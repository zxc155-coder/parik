"""ASGI entry point for production deployments (e.g. uvicorn, Fly.io).

`uvicorn app.asgi:app` serves the FastAPI WebApp on the configured port AND
spawns the Telegram long-polling bot as a background task during the FastAPI
lifespan. Both shut down cleanly together.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.ai_client import CanopyWaveClient
from app.bot.handlers import build_router
from app.config import load_settings
from app.webapp.server import create_app

logger = logging.getLogger("zabolot.asgi")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


async def _run_bot_polling(settings, ai: CanopyWaveClient) -> None:
    from aiogram import Bot, Dispatcher
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

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

    me = await bot.get_me()
    logger.info("Bot started: @%s (id=%s)", me.username, me.id)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except asyncio.CancelledError:
        logger.info("Bot polling cancelled — shutting down")
        raise
    finally:
        await bot.session.close()


def _build_app() -> FastAPI:
    settings = load_settings()
    ai = CanopyWaveClient(
        api_key=settings.canopywave_api_key,
        base_url=settings.canopywave_base_url,
        text_model=settings.text_model,
        vision_model=settings.vision_model,
        vision_api_key=settings.vision_api_key,
        vision_base_url=settings.vision_base_url,
    )

    static_dir = Path(__file__).resolve().parent.parent / "webapp_static"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        bot_task = asyncio.create_task(_run_bot_polling(settings, ai), name="bot-polling")
        try:
            yield
        finally:
            bot_task.cancel()
            try:
                await bot_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            await ai.aclose()

    fastapi_app = create_app(
        ai=ai,
        bot_token=settings.bot_token,
        static_dir=static_dir,
        allowed_user_ids=settings.allowed_ids,
    )
    fastapi_app.router.lifespan_context = lifespan
    return fastapi_app


app = _build_app()
