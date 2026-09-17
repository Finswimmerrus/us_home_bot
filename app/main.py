from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings
from app.handlers.fsm import storage
from app.handlers.sections import router as sections_router
from app.handlers.start import router as start_router
from app.middleware import ContextMiddleware, SessionMiddleware, register_error_handler
from app.utils import setup_logging
from app.database import dispose_engine

logger = logging.getLogger(__name__)


async def run() -> None:
    settings.validate_for_start()
    setup_logging(settings.LOG_LEVEL)

    bot = Bot(token=settings.BOT_TOKEN.get_secret_value())
    dispatcher = Dispatcher(storage=storage)
    dispatcher.message.middleware(SessionMiddleware())
    dispatcher.callback_query.middleware(SessionMiddleware())
    dispatcher.message.middleware(ContextMiddleware())
    dispatcher.callback_query.middleware(ContextMiddleware())
    register_error_handler(dispatcher)
    dispatcher.include_router(start_router)
    dispatcher.include_router(sections_router)

    logger.info("Couple Bot started")
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
        await dispose_engine()
        logger.info("Couple Bot stopped")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
