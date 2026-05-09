"""Telegram bot handlers for chat, photo, and inline modes."""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict, deque
from typing import Any

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    ChosenInlineResult,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
    WebAppInfo,
)

from app.ai_client import AIError, CanopyWaveClient

logger = logging.getLogger(__name__)

# Per-chat rolling history of recent messages (text only). Keeps memory bounded.
_HISTORY_MAX = 12
_history: dict[int, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=_HISTORY_MAX))

# Cache mapping inline result_id -> (query_text, expires_at). The chosen_inline_result
# handler reads from here to look up the original question. ~5 min TTL.
_inline_cache: dict[str, tuple[str, float]] = {}
_INLINE_TTL = 300.0


def _inline_cache_set(result_id: str, query: str) -> None:
    import time as _t

    _inline_cache[result_id] = (query, _t.time() + _INLINE_TTL)
    # Cheap GC
    if len(_inline_cache) > 500:
        now = _t.time()
        for k in list(_inline_cache.keys()):
            if _inline_cache[k][1] < now:
                _inline_cache.pop(k, None)


def _inline_cache_pop(result_id: str) -> str | None:
    item = _inline_cache.pop(result_id, None)
    if not item:
        return None
    return item[0]


def _push(chat_id: int, role: str, content: str) -> None:
    _history[chat_id].append({"role": role, "content": content})


def _history_for(chat_id: int) -> list[dict[str, Any]]:
    return list(_history[chat_id])


def _is_allowed(user_id: int | None, allowed: set[int]) -> bool:
    if not allowed:
        return True
    if user_id is None:
        return False
    return user_id in allowed


def build_router(
    ai: CanopyWaveClient,
    *,
    webapp_url: str = "",
    allowed_user_ids: set[int] | None = None,
) -> Router:
    """Construct an aiogram Router with all handlers wired to the AI client."""
    router = Router(name="zabolot")
    allowed = allowed_user_ids or set()

    @router.message(CommandStart())
    async def on_start(message: Message) -> None:
        if not _is_allowed(message.from_user.id if message.from_user else None, allowed):
            await message.answer("⛔ Доступ к боту ограничен.")
            return
        kb_rows: list[list[InlineKeyboardButton]] = []
        if webapp_url:
            kb_rows.append(
                [
                    InlineKeyboardButton(
                        text="🚀 Открыть веб-приложение",
                        web_app=WebAppInfo(url=webapp_url),
                    )
                ]
            )
        kb_rows.append([InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")])
        kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

        text = (
            "👋 Привет! Я <b>zabolotAI</b> — умный ассистент на базе MiniMax M2.5.\n\n"
            "Что я умею:\n"
            "• 💬 Отвечать на текстовые вопросы\n"
            "• 🖼 Анализировать фото — просто пришли картинку\n"
            "• 🌐 Работать в любом чате через inline: <code>@zabolotrobot вопрос</code>\n"
        )
        if webapp_url:
            text += "• 🚀 Открыть полноценный чат-интерфейс через кнопку ниже\n"
        text += "\nКоманды: /reset — очистить контекст, /help — справка."
        await message.answer(text, reply_markup=kb, parse_mode="HTML")

    HELP_TEXT = (
        "Просто напиши вопрос или пришли фото — я отвечу.\n"
        "В любом другом чате: <code>@zabolotrobot вопрос</code> — мой ответ появится прямо там.\n"
        "/reset — забыть историю разговора."
    )

    @router.message(Command("help"))
    async def on_help(message: Message) -> None:
        await message.answer(HELP_TEXT, parse_mode="HTML")

    @router.callback_query(F.data == "help")
    async def on_help_callback(callback: CallbackQuery) -> None:
        if callback.message is not None:
            try:
                await callback.message.answer(HELP_TEXT, parse_mode="HTML")
            except TelegramBadRequest:
                pass
        try:
            await callback.answer()
        except TelegramBadRequest:
            pass

    @router.message(Command("reset"))
    async def on_reset(message: Message) -> None:
        _history.pop(message.chat.id, None)
        await message.answer("🧹 Контекст разговора очищен.")

    @router.message(F.photo)
    async def on_photo(message: Message, bot: Bot) -> None:
        if not _is_allowed(message.from_user.id if message.from_user else None, allowed):
            return
        await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        # Largest available photo size
        photo = message.photo[-1]  # type: ignore[index]
        file = await bot.get_file(photo.file_id)
        buf = await bot.download_file(file.file_path)  # type: ignore[arg-type]
        if buf is None:
            await message.answer("Не удалось скачать фото :(")
            return
        image_bytes = buf.read()
        prompt = (message.caption or "").strip() or None

        try:
            answer = await ai.chat_with_image(image_bytes, prompt=prompt)
        except AIError as exc:
            logger.warning("vision call failed: %s", exc)
            if exc.status_code == 403:
                await message.answer(
                    "🖼 Распознавание фото пока недоступно: текущий API-ключ "
                    "не имеет доступа к vision-моделям. Попроси админа подключить "
                    "vision-провайдера в <code>.env</code> (<code>VISION_API_KEY</code>, "
                    "<code>VISION_BASE_URL</code>, <code>VISION_MODEL</code>) или апгрейднуть тариф.",
                    parse_mode="HTML",
                )
            else:
                await message.answer(f"Ошибка распознавания: {exc}")
            return
        except Exception as exc:
            logger.exception("vision call failed")
            await message.answer(f"Ошибка распознавания: {exc}")
            return

        if not answer:
            answer = "Не получилось ничего разобрать на фото."

        _push(message.chat.id, "user", f"[Фото]{(' ' + prompt) if prompt else ''}")
        _push(message.chat.id, "assistant", answer)
        await _send_long(message, answer)

    @router.message(F.text)
    async def on_text(message: Message, bot: Bot) -> None:
        if not _is_allowed(message.from_user.id if message.from_user else None, allowed):
            return
        text = (message.text or "").strip()
        if not text:
            return
        await bot.send_chat_action(message.chat.id, ChatAction.TYPING)

        history = _history_for(message.chat.id)
        history.append({"role": "user", "content": text})
        try:
            answer = await ai.chat(history)  # type: ignore[arg-type]
        except Exception as exc:
            logger.exception("text call failed")
            await message.answer(f"Ошибка нейросети: {exc}")
            return
        if not answer:
            answer = "(пустой ответ)"
        _push(message.chat.id, "user", text)
        _push(message.chat.id, "assistant", answer)
        await _send_long(message, answer)

    @router.inline_query()
    async def on_inline(query: InlineQuery) -> None:
        """Answer inline queries instantly with a placeholder; the AI call happens
        in `on_chosen_inline_result`, which then edits the resulting chat message."""
        if not _is_allowed(query.from_user.id, allowed):
            await query.answer(results=[], cache_time=1, is_personal=True)
            return
        q = (query.query or "").strip()
        if not q:
            empty = InlineQueryResultArticle(
                id="empty",
                title="Введите вопрос…",
                description="@zabolotrobot ваш вопрос",
                input_message_content=InputTextMessageContent(
                    message_text="Использование: @zabolotrobot <ваш вопрос>"
                ),
            )
            try:
                await query.answer(results=[empty], cache_time=1, is_personal=True)
            except TelegramBadRequest:
                pass
            return

        # Stable result_id derived from the query so duplicate inline_queries don't
        # generate new placeholders for the same prompt within Telegram's cache window.
        result_id = hashlib.md5(q.encode("utf-8")).hexdigest()[:32]
        _inline_cache_set(result_id, q)

        placeholder_text = f"<b>❓ {_escape_html(q)}</b>\n\n🤔 <i>zabolotAI думает…</i>"
        result = InlineQueryResultArticle(
            id=result_id,
            title=f"Спросить zabolotAI: {q[:55]}",
            description="MiniMax M2.5 ответит прямо в чате",
            input_message_content=InputTextMessageContent(
                message_text=placeholder_text,
                parse_mode="HTML",
            ),
        )
        try:
            await query.answer(results=[result], cache_time=0, is_personal=True)
        except TelegramBadRequest as exc:
            logger.warning("inline answer failed: %s", exc)

    @router.chosen_inline_result()
    async def on_chosen_inline_result(chosen: ChosenInlineResult, bot: Bot) -> None:
        """User picked our inline result — now actually call the AI and edit the message."""
        if not _is_allowed(chosen.from_user.id, allowed):
            return
        inline_message_id = chosen.inline_message_id
        if not inline_message_id:
            logger.warning("chosen_inline_result without inline_message_id (chat-bound chat?)")
            return

        # Prefer cached query; fall back to chosen.query (Telegram passes it through).
        q = _inline_cache_pop(chosen.result_id) or (chosen.query or "").strip()
        if not q:
            try:
                await bot.edit_message_text(
                    inline_message_id=inline_message_id,
                    text="(пустой запрос)",
                )
            except TelegramBadRequest:
                pass
            return

        try:
            answer = await ai.chat([{"role": "user", "content": q}], max_tokens=900)
        except Exception as exc:
            logger.exception("inline AI call failed")
            answer = f"⚠️ Ошибка нейросети: {exc}"

        if not answer:
            answer = "(пустой ответ)"

        truncated = answer if len(answer) <= 3800 else answer[:3800] + "…"
        text = f"<b>❓ {_escape_html(q)}</b>\n\n{_escape_html(truncated)}"
        try:
            await bot.edit_message_text(
                inline_message_id=inline_message_id,
                text=text,
                parse_mode="HTML",
            )
        except TelegramBadRequest as exc:
            logger.warning("edit_message_text failed: %s", exc)

    return router


def _escape_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def _send_long(message: Message, text: str) -> None:
    """Send `text`, splitting into multiple Telegram messages if too long.

    The bot is initialised with `parse_mode=HTML` by default, so AI answers
    that contain unbalanced angle brackets or ampersands trip Telegram's HTML
    parser. On `TelegramBadRequest` we retry with `parse_mode=None` so the
    user always receives the raw text instead of nothing.
    """
    LIMIT = 4000

    async def _send(chunk: str) -> None:
        try:
            await message.answer(chunk)
        except TelegramBadRequest:
            await message.answer(chunk, parse_mode=None)

    if len(text) <= LIMIT:
        await _send(text)
        return
    remaining = text
    while remaining:
        await _send(remaining[:LIMIT])
        remaining = remaining[LIMIT:]
