"""FastAPI server that serves the Telegram Web App and exposes a chat API."""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.ai_client import CanopyWaveClient
from app.webapp.auth import validate_init_data

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    init_data: str = Field(..., description="Telegram WebApp initData string")
    messages: list[dict[str, Any]] = Field(default_factory=list)
    image_base64: str | None = Field(default=None, description="Optional image (data URL or pure base64)")
    image_mime: str = Field(default="image/jpeg")


class ChatResponse(BaseModel):
    answer: str
    user_id: int | None = None


def create_app(
    *,
    ai: CanopyWaveClient,
    bot_token: str,
    static_dir: Path,
    allowed_user_ids: set[int] | None = None,
    skip_auth: bool = False,
) -> FastAPI:
    app = FastAPI(title="zabolot-bot WebApp", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    allowed = allowed_user_ids or set()

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/chat", response_model=ChatResponse)
    async def chat(req: ChatRequest) -> ChatResponse:
        user_id: int | None = None
        if skip_auth:
            logger.warning("skip_auth=True — accepting WebApp request without verification")
        else:
            try:
                data = validate_init_data(req.init_data, bot_token)
            except ValueError as exc:
                logger.warning("WebApp auth failed: %s", exc)
                raise HTTPException(status_code=401, detail=f"invalid init_data: {exc}") from exc
            user = data.get("user") or {}
            if isinstance(user, dict):
                user_id = user.get("id")

            if allowed and (user_id is None or user_id not in allowed):
                raise HTTPException(status_code=403, detail="forbidden")

        if not req.messages and not req.image_base64:
            raise HTTPException(status_code=400, detail="no messages and no image")

        try:
            if req.image_base64:
                raw = req.image_base64
                if raw.startswith("data:"):
                    # data URL: data:image/png;base64,XXXX
                    _, _, b64 = raw.partition(",")
                else:
                    b64 = raw
                try:
                    image_bytes = base64.b64decode(b64)
                except Exception as exc:
                    raise HTTPException(status_code=400, detail=f"bad image base64: {exc}") from exc
                # Last user text message acts as the prompt
                prompt = ""
                history: list[dict[str, Any]] = []
                for m in req.messages:
                    if m.get("role") == "user":
                        prompt = str(m.get("content") or "")
                    else:
                        history.append(m)
                answer = await ai.chat_with_image(
                    image_bytes,
                    prompt=prompt or None,
                    mime_type=req.image_mime,
                    history=history,
                )
            else:
                answer = await ai.chat(req.messages)
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("AI call failed")
            raise HTTPException(status_code=502, detail=f"AI error: {exc}") from exc

        return ChatResponse(answer=answer, user_id=user_id)

    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(static_dir / "index.html")

        @app.get("/{path:path}")
        async def static_fallback(path: str) -> FileResponse:
            target = static_dir / path
            if target.exists() and target.is_file():
                return FileResponse(target)
            return FileResponse(static_dir / "index.html")
    else:
        logger.warning("static_dir %s does not exist; Web App UI not served", static_dir)

    return app
