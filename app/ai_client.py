"""Async client for the Canopy Wave OpenAI-compatible API.

We use the chat-completions endpoint for both text and vision (multi-modal) calls.
The reasoning text models (like minimax-m2.5) emit `<think>...</think>` blocks which
we strip from the user-facing response.
"""

from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Strip <think>...</think> blocks (and any unclosed leading "<think>...") that some
# reasoning models include. We also remove an unmatched dangling "<think>..." prefix.
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_DANGLING_THINK_RE = re.compile(r"^\s*<think>.*?(?:</think>|$)", re.DOTALL | re.IGNORECASE)

DEFAULT_SYSTEM_PROMPT = (
    "Ты дружелюбный, умный AI-ассистент в Telegram. "
    "Отвечай по-русски кратко и по делу, если пользователь не просит подробного ответа. "
    "Используй markdown-форматирование Telegram (жирный, курсив, списки) умеренно."
)

VISION_SYSTEM_PROMPT = (
    "Ты AI-ассистент с возможностью анализа изображений. "
    "Внимательно опиши, что изображено на картинке, и ответь на вопрос пользователя, если он есть. "
    "Отвечай по-русски."
)


def clean_response(text: str) -> str:
    """Remove <think> reasoning blocks from model output and trim whitespace."""
    if not text:
        return ""
    cleaned = _THINK_BLOCK_RE.sub("", text)
    cleaned = _DANGLING_THINK_RE.sub("", cleaned)
    return cleaned.strip()


@dataclass
class ChatMessage:
    role: str
    content: str

    def as_dict(self) -> dict[str, Any]:
        return {"role": self.role, "content": self.content}


class AIError(RuntimeError):
    """Raised when the upstream AI API returns a non-200 response."""

    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"AI API returned {status_code}: {body}")
        self.status_code = status_code
        self.body = body


class CanopyWaveClient:
    """Tiny OpenAI-compatible client targeting Canopy Wave (optionally a separate vision provider)."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.canopywave.io/v1",
        text_model: str = "minimax/minimax-m2.5",
        vision_model: str = "zai/glm-5.1",
        vision_api_key: str | None = None,
        vision_base_url: str | None = None,
        inline_model: str = "openai/gpt-oss-20b:free",
        inline_api_key: str | None = None,
        inline_base_url: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.text_model = text_model
        self.vision_model = vision_model
        self.vision_api_key = (vision_api_key or "").strip() or api_key
        self.vision_base_url = ((vision_base_url or "").strip() or base_url).rstrip("/")
        # Inline routing defaults to the vision provider (typically OpenRouter)
        # because that's where the FAST free models live; override individually
        # via INLINE_API_KEY / INLINE_BASE_URL env if you want a third provider.
        self.inline_model = inline_model
        self.inline_api_key = (inline_api_key or "").strip() or self.vision_api_key
        self.inline_base_url = (
            (inline_base_url or "").strip() or self.vision_base_url
        ).rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _provider_creds(self, provider: str | None) -> tuple[str, str]:
        """Resolve (base_url, api_key) for a logical provider name.

        Recognised providers: ``"canopywave"`` (default text route) and
        ``"openrouter"`` (the same provider used for vision/inline). Anything
        else falls back to the canopywave defaults.
        """
        if provider == "openrouter":
            return self.vision_base_url, self.vision_api_key
        return self.base_url, self.api_key

    async def chat(
        self,
        messages: list[ChatMessage] | list[dict[str, Any]],
        *,
        model: str | None = None,
        provider: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        system_prompt: str | None = DEFAULT_SYSTEM_PROMPT,
    ) -> str:
        """Plain text chat completion. Returns assistant's text content.

        ``provider`` selects the upstream API: ``"canopywave"`` (default) or
        ``"openrouter"``. The same OpenRouter credentials used for vision are
        reused when ``provider="openrouter"``.
        """
        msg_list: list[dict[str, Any]] = []
        if system_prompt:
            msg_list.append({"role": "system", "content": system_prompt})
        for m in messages:
            msg_list.append(m.as_dict() if isinstance(m, ChatMessage) else m)

        payload = {
            "model": model or self.text_model,
            "messages": msg_list,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        base_url, api_key = self._provider_creds(provider)
        return await self._call(payload, base_url=base_url, api_key=api_key)

    async def chat_inline(
        self,
        query: str,
        *,
        max_tokens: int = 400,
        timeout: float = 8.0,
    ) -> str:
        """Fast, single-shot completion for inline queries.

        Uses the inline model + provider (typically OpenRouter `gpt-oss-20b:free`)
        and applies a tight per-call timeout so we always respond inside Telegram's
        ~10s inline_query window.
        """
        payload = {
            "model": self.inline_model,
            "messages": [
                {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
            "temperature": 0.5,
            "max_tokens": max_tokens,
        }
        return await self._call(
            payload,
            base_url=self.inline_base_url,
            api_key=self.inline_api_key,
            timeout=timeout,
        )

    async def chat_with_image(
        self,
        image_bytes: bytes,
        prompt: str | None = None,
        *,
        mime_type: str = "image/jpeg",
        model: str | None = None,
        max_tokens: int = 1024,
        history: list[dict[str, Any]] | None = None,
    ) -> str:
        """Multi-modal chat: send an image with optional text prompt."""
        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{mime_type};base64,{b64}"

        user_content: list[dict[str, Any]] = []
        if prompt:
            user_content.append({"type": "text", "text": prompt})
        else:
            user_content.append(
                {
                    "type": "text",
                    "text": "Опиши, что на изображении, и ответь на любые вопросы по нему.",
                }
            )
        user_content.append({"type": "image_url", "image_url": {"url": data_url}})

        msg_list: list[dict[str, Any]] = [{"role": "system", "content": VISION_SYSTEM_PROMPT}]
        if history:
            msg_list.extend(history)
        msg_list.append({"role": "user", "content": user_content})

        payload = {
            "model": model or self.vision_model,
            "messages": msg_list,
            "max_tokens": max_tokens,
        }
        return await self._call(
            payload,
            base_url=self.vision_base_url,
            api_key=self.vision_api_key,
        )

    async def _call(
        self,
        payload: dict[str, Any],
        *,
        base_url: str,
        api_key: str,
        timeout: float | None = None,
    ) -> str:
        url = f"{base_url}/chat/completions"
        try:
            resp = await self._client.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=timeout if timeout is not None else self._client.timeout,
            )
        except httpx.HTTPError as exc:
            logger.error("HTTP error calling AI: %s", exc)
            raise

        if resp.status_code != 200:
            logger.error("AI API error %s: %s", resp.status_code, resp.text[:500])
            raise AIError(resp.status_code, resp.text[:500])

        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"AI response had no choices: {data}")
        msg = choices[0].get("message", {}) or {}
        content = msg.get("content") or ""
        return clean_response(content)
