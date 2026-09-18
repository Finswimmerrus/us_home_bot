from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal

logger = logging.getLogger(__name__)


class SessionMiddleware(BaseMiddleware):
    """Provides a single AsyncSession per update. Commits on success, rolls back on error."""

    def __init__(self, session_maker=None) -> None:
        self._session_maker = session_maker or SessionLocal

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, object]], Awaitable[object]],
        event: TelegramObject,
        data: dict[str, object],
    ) -> object:
        if "session" in data:
            return await handler(event, data)

        session: AsyncSession = self._session_maker()
        data["session"] = session
        try:
            result = await handler(event, data)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            logger.exception("Session rolled back due to error")
            raise
        finally:
            await session.close()


def session_middleware(session_maker=None) -> SessionMiddleware:
    return SessionMiddleware(session_maker=session_maker)
