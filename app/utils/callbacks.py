from __future__ import annotations

import logging

from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ValidationError
from app.services.couple_service import CoupleService
from app.utils.context import Context

logger = logging.getLogger(__name__)

SKIP_VALUES: frozenset[str] = frozenset({"", "пропустить", "/пропустить", "skip", "/skip", "-"})
CANCEL_BUTTON = "Отмена"
SKIP_BUTTON = "Пропустить"
SECTION_BACK = "section:back"


def inline_keyboard(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=data) for text, data in row]
            for row in rows
        ]
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=CANCEL_BUTTON)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def optional_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=SKIP_BUTTON)],
            [KeyboardButton(text=CANCEL_BUTTON)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def section_back_keyboard(callback_data: str = SECTION_BACK) -> InlineKeyboardMarkup:
    return inline_keyboard([[("Назад", callback_data)]])


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return inline_keyboard([[("В главное меню", SECTION_BACK)]])


def couple_join_kb() -> InlineKeyboardMarkup:
    return inline_keyboard(
        [
            [("Присоединиться по коду", "couple:join")],
            [("Создать пару", "couple:create")],
            [("Показать код приглашения", "couple:show_code")],
        ]
    )


def get_callback_message(callback: CallbackQuery) -> Message | None:
    message = callback.message
    if isinstance(message, Message):
        return message
    return None


async def answer_callback(callback: CallbackQuery, text: str | None = None, alert: bool = False) -> None:
    try:
        await callback.answer(text, show_alert=alert)
    except TelegramAPIError:
        logger.exception("Failed to answer callback query")


async def reply_callback(
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | None = None,
    parse_mode: str | None = None,
) -> None:
    await answer_callback(callback)
    message = get_callback_message(callback)
    if message is not None:
        try:
            await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except TelegramAPIError:
            logger.exception("Failed to send callback reply message")


async def alert_callback(callback: CallbackQuery, text: str) -> None:
    await answer_callback(callback, text=text, alert=True)


def require_user_id(context: Context) -> int:
    if context.user_id is None:
        raise ValidationError("Не удалось определить пользователя", field="user_id")
    return context.user_id


async def get_couple(session: AsyncSession, user_id: int):
    couple = await CoupleService(session).get_user_couple(user_id)
    if couple is None:
        raise ValidationError("Сначала создайте или присоединитесь к паре", field="couple")
    return couple


def callback_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Некорректный идентификатор", field="id") from exc
