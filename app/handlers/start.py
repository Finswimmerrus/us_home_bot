from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, Message

from app.handlers.fsm import storage
from app.services.couple_service import UserService
from app.utils.context import Context

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

SECTION_BACK = "section:back"


def section_back_kb() -> InlineKeyboardMarkup:
    from aiogram.types import InlineKeyboardButton
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data=SECTION_BACK)]]
    )


def couple_join_kb(code: str) -> InlineKeyboardMarkup:
    from aiogram.types import InlineKeyboardButton
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Присоединиться по коду", callback_data="couple:join")],
            [InlineKeyboardButton(text="Создать пару", callback_data="couple:create")],
            [InlineKeyboardButton(text="Код приглашения", callback_data="couple:show_code")],
        ]
    )


@router.message(Command("start"))
async def cmd_start(message: Message, context: Context, session) -> Message:
    service = UserService(session)
    result = await service.handle_start(
        telegram_id=context.user_id,
        username=context.telegram_user.username if context.telegram_user else None,
        first_name=context.telegram_user.first_name if context.telegram_user else None,
    )
    user = result["user"]
    couple = result["couple"]

    name = user.display_name or user.first_name or user.username or f"User{user.id}"
    if couple is None:
        text = (
            f"Привет, {name}!\n\n"
            "Ты ещё не состояишь в паре. Создай пару или присоединись по коду."
        )
        await message.answer(text, reply_markup=couple_join_kb(couple.invite_code if couple else ""))
    else:
        text = (
            f"Привет, {name}!\n\n"
            f"Пара: {couple.name}\n"
            "Выбери раздел:"
        )
        await message.answer(text, reply_markup=MAIN_MENU)
    return message


@router.callback_query(lambda c: c.data == "couple:create")
async def cb_create_couple(callback: CallbackQuery, context: Context, session) -> None:
    service = UserService(session)
    user = await service._couple_service.get_or_create_user(
        context.user_id,
        context.telegram_user.username if context.telegram_user else None,
        context.telegram_user.first_name if context.telegram_user else None,
    )
    couple, member = await service._couple_service.create_couple(user, name="Наша пара")
    await callback.message.answer(
        f"Пара «{couple.name}» создана!\nКод приглашения: {couple.invite_code}",
        reply_markup=MAIN_MENU,
    )
    await callback.answer("Пара создана")


@router.callback_query(lambda c: c.data == "couple:join")
async def cb_join_couple(callback: CallbackQuery, context: Context, session) -> None:
    await callback.message.answer(
        "Отправь код приглашения в формате: /join КОД\n"
        "Или введи код в ответ на это сообщение.",
        reply_markup=section_back_kb(),
    )
    await callback.answer()


@router.message(lambda m: m.text and m.text.startswith("/join "))
async def cmd_join(message: Message, context: Context, session) -> Message:
    code = message.text.split(" ", 1)[1].strip().upper()
    service = UserService(session)
    user = await service._couple_service.get_or_create_user(
        context.user_id,
        context.telegram_user.username if context.telegram_user else None,
        context.telegram_user.first_name if context.telegram_user else None,
    )
    couple = await service._couple_service.find_couple_by_code(code)
    if couple is None:
        await message.answer("Код приглашения недействителен или истёк.")
        return message
    member = await service._couple_service.join_couple(user, couple)
    if member is None:
        await message.answer("Ты уже состояишь в этой паре.")
        return message
    await message.answer(
        f"Ты присоединился к паре «{couple.name}»!",
        reply_markup=MAIN_MENU,
    )
    return message


@router.message(lambda m: m.text and m.text.startswith("/join"))
async def cmd_join_short(message: Message, context: Context, session) -> Message:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Используй: /join КОД")
        return message
    return await cmd_join(message, context, session)


@router.callback_query(lambda c: c.data == "couple:show_code")
async def cb_show_code(callback: CallbackQuery, context: Context, session) -> None:
    service = UserService(session)
    couple = await service._couple_service.get_user_couple(context.user_id)
    if couple is None:
        await callback.answer("У тебя нет пары", show_alert=True)
        return
    code = couple.invite_code
    if not code:
        await callback.answer("Код приглашения недоступен", show_alert=True)
        return
    await callback.message.answer(f"Код приглашения: {code}")
    await callback.answer()


@router.message(lambda m: m.text == "О паре")
async def btn_couple_info(message: Message, context: Context, session) -> Message:
    service = UserService(session)
    couple = await service._couple_service.get_user_couple(context.user_id)
    if couple is None:
        await message.answer("Ты не состояишь в паре.", reply_markup=couple_join_kb(""))
        return message
    members = await service._couple_service.get_couple_members(couple.id)
    names = []
    for m in members:
        names.append(m.display_name or m.first_name or m.username or str(m.id))
    text = (
        f"Пара: {couple.name}\n"
        f"Участники: {', '.join(names)}"
    )
    await message.answer(text, reply_markup=MAIN_MENU)
    return message


@router.callback_query(lambda c: c.data == SECTION_BACK)
async def cb_section_back(callback: CallbackQuery, context: Context, session) -> None:
    await callback.message.answer("Главное меню:", reply_markup=MAIN_MENU)
    await callback.answer()