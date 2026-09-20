from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from aiogram.types import User as TelegramUser

from app.services.couple_service import CoupleService
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
        user_id = None
        timezone = "UTC"
        if telegram_user is not None:
            user = await CoupleService(data["session"]).get_or_create_user(
                telegram_user.id, telegram_user.username, telegram_user.first_name
            )
            user_id = user.id
            timezone = user.timezone

        context = build_context(
            user_id=user_id,
            telegram_user=telegram_user,
            timezone=timezone,
        )
        data["context"] = context
        data["user_id"] = user_id
        return await handler(event, data)
