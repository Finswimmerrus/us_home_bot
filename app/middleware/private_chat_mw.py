from __future__ import annotations

from collections.abc import Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message, TelegramObject


class PrivateChatMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, object]], Awaitable[object]],
        event: TelegramObject,
        data: dict[str, object],
    ) -> object | None:
        message = event if isinstance(event, Message) else None
        if isinstance(event, CallbackQuery) and isinstance(event.message, Message):
            message = event.message
        if message is None or message.chat.type != ChatType.PRIVATE:
            return None
        return await handler(event, data)
