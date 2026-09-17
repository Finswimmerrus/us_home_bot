from __future__ import annotations

import logging
from typing import Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TelegramUser

from app.utils.context import build_context

logger = logging.getLogger(__name__)


class ContextMiddleware(BaseMiddleware):
    """Builds a Context object for every update and injects it as data["context"]."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, object]], Awaitable[object]],
        event: TelegramObject,
        data: dict[str, object],
    ) -> object:
        telegram_user: TelegramUser | None = getattr(event, "from_user", None)
        user_id = telegram_user.id if telegram_user else None

        context = build_context(
            user_id=user_id,
            telegram_user=telegram_user,
        )
        data["context"] = context
        data["user_id"] = user_id
        return await handler(event, data)