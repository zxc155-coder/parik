"""Entry point: runs the Telegram bot (long-polling) and the FastAPI Web App server.

Both run in the same asyncio loop, so a single `python -m app.main` is enough.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.ai_client import CanopyWaveClient
from app.bot.handlers import build_router
from app.config import load_settings
from app.webapp.server import create_app

logger = logging.getLogger("zabolot")


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def _run_bot(settings, ai: CanopyWaveClient) -> None:
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
        # Drop pending updates to avoid old-message storms on restart
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


async def _run_web(settings, ai: CanopyWaveClient) -> None:
    static_dir = Path(__file__).resolve().parent.parent / "webapp_static"
    app = create_app(
        ai=ai,
        bot_token=settings.bot_token,
        static_dir=static_dir,
        allowed_user_ids=settings.allowed_ids,
    )
    config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)
    logger.info("WebApp server starting on %s:%s", settings.host, settings.port)
    await server.serve()


async def amain(*, run_bot: bool = True, run_web: bool = True) -> None:
    _setup_logging()
    settings = load_settings()
    ai = CanopyWaveClient(
        api_key=settings.canopywave_api_key,
        base_url=settings.canopywave_base_url,
        text_model=settings.text_model,
        vision_model=settings.vision_model,
        vision_api_key=settings.vision_api_key,
        vision_base_url=settings.vision_base_url,
    )

    tasks: list[asyncio.Task] = []
    if run_bot:
        tasks.append(asyncio.create_task(_run_bot(settings, ai), name="bot"))
    if run_web:
        tasks.append(asyncio.create_task(_run_web(settings, ai), name="web"))

    if not tasks:
        logger.error("Nothing to run: pass --bot and/or --web")
        return

    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        for t in pending:
            t.cancel()
        for t in done:
            exc = t.exception()
            if exc:
                logger.error("Task %s crashed: %s", t.get_name(), exc)
                raise exc
    finally:
        await ai.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run zabolot-bot")
    parser.add_argument("--no-bot", action="store_true", help="Skip Telegram bot polling")
    parser.add_argument("--no-web", action="store_true", help="Skip WebApp server")
    args = parser.parse_args()
    asyncio.run(amain(run_bot=not args.no_bot, run_web=not args.no_web))


if __name__ == "__main__":
    main()
