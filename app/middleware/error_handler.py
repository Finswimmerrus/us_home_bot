from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from aiogram import BaseMiddleware, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message, TelegramObject

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
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Unhandled exception")
            await self._reply_error(event, "Внутренняя ошибка. Попробуйте позже.")
            raise

    async def _reply_error(self, event: TelegramObject, text: str) -> None:
        try:
            if isinstance(event, CallbackQuery):
                message = event.message if isinstance(event.message, Message) else None
                if isinstance(message, Message):
                    await message.answer(text)
                else:
                    await event.answer(text, show_alert=True)
                return
            if isinstance(event, Message):
                await event.answer(text)
                return
            fallback = getattr(event, "message", None)
            if isinstance(fallback, Message):
                await fallback.answer(text)
        except TelegramAPIError:
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
