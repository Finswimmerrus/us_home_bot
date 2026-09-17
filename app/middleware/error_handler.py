from __future__ import annotations

import logging
from typing import Awaitable, Callable

from aiogram import BaseMiddleware, Router
from aiogram.types import TelegramObject, Update

from app.exceptions import DomainError

logger = logging.getLogger(__name__)


class GlobalErrorHandler(BaseMiddleware):
    """Catches DomainError and unexpected exceptions, logging and replying safely."""

    def __init__(self, router: Router | None = None) -> None:
        self._router = router

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, object]], Awaitable[object]],
        event: TelegramObject,
        data: dict[str, object],
    ) -> object:
        try:
            return await handler(event, data)
        except DomainError as exc:
            logger.warning("DomainError: %s (code=%s)", exc.message, exc.code)
            await self._reply_error(event, exc.message)
            return None
        except Exception as exc:
            logger.exception("Unhandled exception")
            await self._reply_error(event, "Внутренняя ошибка. Попробуйте позже.")
            return None

    async def _reply_error(self, event: TelegramObject, text: str) -> None:
        message = getattr(event, "message", None) or getattr(event, "callback_query", None)
        if message is None:
            return
        try:
            if hasattr(message, "edit_text") and getattr(message, "callback_query", None) is not None:
                await message.edit_text(text)
            elif hasattr(message, "answer"):
                await message.answer(text)
        except Exception:
            logger.exception("Failed to send error reply")


def register_error_handler(router: Router) -> GlobalErrorHandler:
    middleware = GlobalErrorHandler(router=router)
    router.message.middleware(middleware)
    router.callback_query.middleware(middleware)
    router.inline_query.middleware(middleware)
    router.chosen_inline_result.middleware(middleware)
    router.poll.middleware(middleware)
    router.my_chat_member.middleware(middleware)
    router.chat_member.middleware(middleware)
    router.chat_join_request.middleware(middleware)
    return middleware