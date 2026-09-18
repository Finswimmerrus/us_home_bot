from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import Conflict, DomainError
from app.services.couple_service import UserService
from app.utils.callbacks import (
    SECTION_BACK,
    alert_callback,
    couple_join_kb,
    inline_keyboard,
    reply_callback,
    section_back_keyboard,
)
from app.utils.context import Context

logger = logging.getLogger(__name__)

router = Router()

MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Задачи"), KeyboardButton(text="Кино")],
        [KeyboardButton(text="Списки"), KeyboardButton(text="Путешествия")],
        [KeyboardButton(text="Вишлист"), KeyboardButton(text="Заметки")],
        [KeyboardButton(text="Настройки"), KeyboardButton(text="О паре")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)


@router.message(Command("start"))
async def cmd_start(message: Message, context: Context, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    service = UserService(session)
    if context.telegram_user is None:
        await message.answer("Не удалось определить пользователя.")
        return
    result = await service.handle_start(
        telegram_id=context.telegram_user.id,
        username=context.telegram_user.username if context.telegram_user else None,
        first_name=context.telegram_user.first_name if context.telegram_user else None,
    )
    user = result["user"]
    couple = result["couple"]

    name = user.display_name or user.first_name or user.username or f"User{user.id}"
    if couple is None:
        text = (
            f"Привет, {name}!\n\n"
            "Ты ещё не состоишь в паре. Создай пару или присоединись по коду."
        )
        await message.answer(text, reply_markup=couple_join_kb())
    else:
        text = (
            f"Привет, {name}!\n\n"
            f"Пара: {couple.name}\n"
            "Выбери раздел:"
        )
        await message.answer(text, reply_markup=MAIN_MENU)


@router.callback_query(lambda c: c.data == "couple:create")
async def cb_create_couple(
    callback: CallbackQuery, context: Context, session: AsyncSession
) -> None:
    user_id = context.user_id
    if user_id is None:
        await alert_callback(callback, "Не удалось определить пользователя.")
        return
    service = UserService(session)
    telegram = context.telegram_user
    if telegram is None:
        await alert_callback(callback, "Не удалось определить пользователя.")
        return
    user = await service._couple_service.get_or_create_user(
        telegram.id,
        telegram.username if telegram else None,
        telegram.first_name if telegram else None,
    )
    try:
        couple, _ = await service._couple_service.create_couple(user, name="Наша пара")
    except Conflict:
        await alert_callback(callback, "Вы уже состоите в паре.")
        return
    await reply_callback(
        callback,
        f"Пара «{couple.name}» создана!\nКод приглашения: {couple.invite_code}",
        MAIN_MENU,
    )


@router.callback_query(lambda c: c.data == "couple:join")
async def cb_join_couple(callback: CallbackQuery, context: Context, session: AsyncSession) -> None:
    await reply_callback(
        callback,
        "Отправь код приглашения в формате: /join КОД",
        section_back_keyboard(),
    )


@router.message(lambda m: m.text and (m.text == "/join" or m.text.startswith("/join ")))
async def cmd_join(
    message: Message, context: Context, session: AsyncSession
) -> Message | None:
    if not message.text:
        return message
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Используй: /join КОД")
        return message
    code = parts[1].strip().upper()
    user_id = context.user_id
    telegram = context.telegram_user
    if user_id is None:
        await message.answer("Не удалось определить пользователя.")
        return message
    if telegram is None:
        await message.answer("Не удалось определить пользователя.")
        return message
    service = UserService(session)
    user = await service._couple_service.get_or_create_user(
        telegram.id,
        telegram.username if telegram else None,
        telegram.first_name if telegram else None,
    )
    couple = await service._couple_service.find_couple_by_code(code)
    if couple is None:
        await message.answer("Код приглашения недействителен или истёк.")
        return message
    try:
        member = await service._couple_service.join_couple(user, couple)
    except DomainError as exc:
        await message.answer(exc.message)
        return message
    if member is None:
        await message.answer("Ты уже состоишь в этой паре.")
        return message
    await message.answer(f"Ты присоединился к паре «{couple.name}»!", reply_markup=MAIN_MENU)
    return message


@router.callback_query(lambda c: c.data == "couple:show_code")
async def cb_show_code(
    callback: CallbackQuery, context: Context, session: AsyncSession
) -> None:
    user_id = context.user_id
    if user_id is None:
        await alert_callback(callback, "Не удалось определить пользователя.")
        return
    service = UserService(session)
    couple = await service._couple_service.get_user_couple(user_id)
    if couple is None:
        await alert_callback(callback, "У тебя нет пары.")
        return
    code = couple.invite_code
    if not code:
        await alert_callback(callback, "Код приглашения недоступен. Создайте новый код в разделе «О паре».")
        return
    await reply_callback(callback, f"Код приглашения: {code}")


@router.callback_query(lambda c: c.data == "couple:regenerate_code")
async def cb_regenerate_code(callback: CallbackQuery, context: Context, session: AsyncSession) -> None:
    user_id = context.user_id
    if user_id is None:
        await alert_callback(callback, "Не удалось определить пользователя.")
        return
    service = UserService(session)
    couple = await service._couple_service.get_user_couple(user_id)
    if couple is None:
        await alert_callback(callback, "У тебя нет пары.")
        return
    try:
        code = await service._couple_service.regenerate_invite_code(couple.id, user_id)
    except Conflict as exc:
        await alert_callback(callback, exc.message)
        return
    await reply_callback(callback, f"Новый код приглашения: {code}")


@router.callback_query(lambda c: c.data == "couple:leave_confirm")
async def cb_leave_confirm(callback: CallbackQuery) -> None:
    await reply_callback(
        callback,
        "Точно выйти из пары? Общие данные останутся у второго участника.",
        inline_keyboard(
            [
                [("Выйти", "couple:leave")],
                [("Отмена", "couple:menu")],
            ]
        ),
    )


@router.callback_query(lambda c: c.data == "couple:leave")
async def cb_leave_couple(callback: CallbackQuery, context: Context, session: AsyncSession) -> None:
    user_id = context.user_id
    if user_id is None:
        await alert_callback(callback, "Не удалось определить пользователя.")
        return
    service = UserService(session)
    couple = await service._couple_service.get_user_couple(user_id)
    if couple is None:
        await alert_callback(callback, "У тебя нет пары.")
        return
    try:
        await service._couple_service.leave_couple(couple.id, user_id)
    except Conflict as exc:
        await alert_callback(callback, exc.message)
        return
    await reply_callback(callback, "Ты вышел из пары.", couple_join_kb())


@router.callback_query(lambda c: c.data == "couple:delete_confirm")
async def cb_delete_confirm(callback: CallbackQuery) -> None:
    await reply_callback(
        callback,
        "Удалить пару и все общие данные? Это действие нельзя отменить.",
        inline_keyboard(
            [
                [("Удалить пару", "couple:delete")],
                [("Отмена", "couple:menu")],
            ]
        ),
    )


@router.callback_query(lambda c: c.data == "couple:delete")
async def cb_delete_couple(callback: CallbackQuery, context: Context, session: AsyncSession) -> None:
    user_id = context.user_id
    if user_id is None:
        await alert_callback(callback, "Не удалось определить пользователя.")
        return
    service = UserService(session)
    couple = await service._couple_service.get_user_couple(user_id)
    if couple is None:
        await alert_callback(callback, "У тебя нет пары.")
        return
    await service._couple_service.delete_couple(couple.id, user_id)
    await reply_callback(callback, "Пара удалена.", couple_join_kb())


@router.message(lambda m: m.text == "О паре")
async def btn_couple_info(
    message: Message, context: Context, session: AsyncSession
) -> Message | None:
    user_id = context.user_id
    if user_id is None:
        await message.answer("Не удалось определить пользователя.")
        return message
    service = UserService(session)
    couple = await service._couple_service.get_user_couple(user_id)
    if couple is None:
        await message.answer("Ты не состоишь в паре.", reply_markup=couple_join_kb())
        return message
    members = await service._couple_service.get_couple_members(couple.id)
    names = [m.display_name or m.first_name or m.username or str(m.id) for m in members]
    text = (
        f"Пара: {couple.name}\n"
        f"Участники: {', '.join(names)}"
    )
    await message.answer(
        text,
        reply_markup=_couple_menu_keyboard(couple.invite_code),
    )
    return message


def _couple_menu_keyboard(invite_code: str | None) -> InlineKeyboardMarkup:
    rows = []
    if invite_code:
        rows.append([("Показать код", "couple:show_code")])
    rows.append([("Создать новый код", "couple:regenerate_code")])
    rows.append([("Выйти из пары", "couple:leave_confirm")])
    rows.append([("Удалить пару", "couple:delete_confirm")])
    rows.append([("Назад", SECTION_BACK)])
    return inline_keyboard(rows)


@router.callback_query(lambda c: c.data == "couple:menu")
async def cb_couple_menu(callback: CallbackQuery, context: Context, session: AsyncSession) -> None:
    user_id = context.user_id
    if user_id is None:
        await alert_callback(callback, "Не удалось определить пользователя.")
        return
    service = UserService(session)
    couple = await service._couple_service.get_user_couple(user_id)
    if couple is None:
        await reply_callback(callback, "Ты не состоишь в паре.", couple_join_kb())
        return
    members = await service._couple_service.get_couple_members(couple.id)
    names = [m.display_name or m.first_name or m.username or str(m.id) for m in members]
    text = f"Пара: {couple.name}\nУчастники: {', '.join(names)}"
    await reply_callback(
        callback,
        text,
        _couple_menu_keyboard(couple.invite_code),
    )


@router.callback_query(lambda c: c.data == SECTION_BACK)
async def cb_section_back(callback: CallbackQuery, context: Context, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    await reply_callback(callback, "Главное меню:", MAIN_MENU)
