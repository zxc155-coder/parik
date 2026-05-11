"""ASGI entry point for production deployments (e.g. uvicorn, Render, Fly.io).

`uvicorn app.asgi:app` serves the FastAPI WebApp on the configured port. The
Telegram bot runs in one of two modes depending on env config:

* **Polling** (default, dev): a background asyncio task long-polls Telegram.
* **Webhook** (production): when `WEBHOOK_BASE_URL` is set we register a webhook
  at `<base>/webhook` and a FastAPI route hands incoming updates to the
  dispatcher. Required for free plans (Render) that spin down on inactivity —
  every Telegram message becomes an inbound HTTP request that wakes the service.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update
from fastapi import FastAPI, Header, HTTPException, Request

from app.ai_client import CanopyWaveClient
from app.bot.handlers import build_router
from app.config import Settings, load_settings
from app.webapp.server import create_app

logger = logging.getLogger("zabolot.asgi")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def _build_bot(settings: Settings, ai: CanopyWaveClient) -> tuple[Bot, Dispatcher]:
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(
        build_router(
            ai,
            webapp_url=settings.webapp_url,
            allowed_user_ids=settings.allowed_ids,
        )
    )
    return bot, dp


async def _run_bot_polling(bot: Bot, dp: Dispatcher) -> None:
    me = await bot.get_me()
    logger.info("Bot started (polling): @%s (id=%s)", me.username, me.id)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except asyncio.CancelledError:
        logger.info("Bot polling cancelled — shutting down")
        raise
    finally:
        await bot.session.close()


async def _setup_webhook(bot: Bot, dp: Dispatcher, settings: Settings) -> None:
    me = await bot.get_me()
    base = settings.webhook_base_url.rstrip("/")
    url = f"{base}{settings.webhook_path}"
    logger.info("Bot started (webhook): @%s (id=%s) -> %s", me.username, me.id, url)
    await bot.set_webhook(
        url=url,
        secret_token=settings.webhook_secret or None,
        drop_pending_updates=True,
        allowed_updates=dp.resolve_used_update_types(),
    )


def _keepalive_target(settings: Settings) -> str:
    """Resolve the absolute URL we should self-ping for keep-alive.

    Explicit ``keepalive_url`` wins; otherwise we fall back to the public
    health endpoint inferred from ``webhook_base_url``. Returns ``""`` when
    self-pinging should be disabled (local dev / no public URL configured).
    """
    if settings.keepalive_url.strip():
        return settings.keepalive_url.strip()
    if settings.webhook_base_url.strip():
        return f"{settings.webhook_base_url.rstrip('/')}/api/health"
    return ""


async def _run_keepalive(url: str, interval: float) -> None:
    """Periodically GET ``url`` so Render Free doesn't spin the service down.

    Free Render web services sleep after 15 min without inbound HTTP. By having
    the running service GET its own public health endpoint every ~10 minutes,
    the request travels back through Render's edge as inbound traffic and resets
    the idle timer. This is intentionally simple and tolerates transient errors
    by logging and waiting for the next tick.
    """
    logger.info("Keep-alive enabled: pinging %s every %.0fs", url, interval)
    async with httpx.AsyncClient(timeout=20) as client:
        while True:
            try:
                await asyncio.sleep(interval)
                resp = await client.get(url)
                logger.info("Keep-alive ping %s -> %d", url, resp.status_code)
            except asyncio.CancelledError:
                logger.info("Keep-alive cancelled")
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("Keep-alive ping failed: %s", exc)


def _build_app() -> FastAPI:
    settings = load_settings()
    ai = CanopyWaveClient(
        api_key=settings.canopywave_api_key,
        base_url=settings.canopywave_base_url,
        text_model=settings.text_model,
        vision_model=settings.vision_model,
        vision_api_key=settings.vision_api_key,
        vision_api_keys=settings.openrouter_keys,
        vision_base_url=settings.vision_base_url,
        inline_model=settings.inline_model,
        inline_api_key=settings.inline_api_key,
        inline_base_url=settings.inline_base_url,
        ecomagent_api_key=settings.ecomagent_api_key,
        ecomagent_base_url=settings.ecomagent_base_url,
    )

    static_dir = Path(__file__).resolve().parent.parent / "webapp_static"
    bot, dp = _build_bot(settings, ai)
    use_webhook = bool(settings.webhook_base_url.strip())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        polling_task: asyncio.Task | None = None
        keepalive_task: asyncio.Task | None = None
        if use_webhook:
            await _setup_webhook(bot, dp, settings)
        else:
            polling_task = asyncio.create_task(
                _run_bot_polling(bot, dp), name="bot-polling"
            )
        ka_url = _keepalive_target(settings)
        if ka_url:
            keepalive_task = asyncio.create_task(
                _run_keepalive(ka_url, settings.keepalive_interval),
                name="keepalive",
            )
        try:
            yield
        finally:
            if keepalive_task is not None:
                keepalive_task.cancel()
                try:
                    await keepalive_task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
            if polling_task is not None:
                polling_task.cancel()
                try:
                    await polling_task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
            else:
                # Do NOT delete the webhook on shutdown. On platforms with
                # rolling deploys (Render), the new instance calls set_webhook
                # before the old one stops; deleting here would race and leave
                # Telegram with no webhook URL — making the bot silent until
                # the next forced redeploy. Webhooks persist across restarts;
                # the next instance simply overwrites it on startup.
                await bot.session.close()
            await ai.aclose()

    fastapi_app = create_app(
        ai=ai,
        bot_token=settings.bot_token,
        static_dir=static_dir,
        allowed_user_ids=settings.allowed_ids,
    )
    fastapi_app.router.lifespan_context = lifespan

    if use_webhook:

        @fastapi_app.post(settings.webhook_path)
        async def telegram_webhook(
            request: Request,
            x_telegram_bot_api_secret_token: str | None = Header(default=None),
        ) -> dict[str, bool]:
            if settings.webhook_secret:
                if x_telegram_bot_api_secret_token != settings.webhook_secret:
                    raise HTTPException(status_code=403, detail="bad secret token")
            payload = await request.json()
            try:
                update = Update.model_validate(payload, context={"bot": bot})
            except Exception as exc:  # noqa: BLE001
                logger.exception("invalid update payload: %s", exc)
                raise HTTPException(status_code=400, detail="bad update") from exc
            await dp.feed_update(bot, update)
            return {"ok": True}

    return fastapi_app


app = _build_app()
