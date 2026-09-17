import logging
from datetime import date, datetime
from typing import Any

from aiogram import Router
from aiogram.types import Message

from app.services.couple_service import UserService
from app.services.list_service import ListService
from app.services.movie_service import MovieService
from app.services.note_service import NoteService
from app.services.settings_service import SettingsService
from app.services.task_service import TaskService
from app.services.trip_service import TripService
from app.services.wishlist_service import WishlistService
from app.utils.context import Context

router = Router()
logger = logging.getLogger(__name__)

SECTION_LABELS = {
    "Задачи",
    "Кино",
    "Списки",
    "Путешествия",
    "Вишлист",
    "Заметки",
    "Настройки",
}


def _format_date(value: date | datetime | None) -> str:
    if value is None:
        return "без даты"
    return value.strftime("%d.%m.%Y")


def _format_tasks(items: list[Any]) -> str:
    if not items:
        return "Задач пока нет."
    return "Задачи:\n" + "\n".join(
        f"• {item.title} — {item.status}" for item in items
    )


def _format_movies(items: list[Any]) -> str:
    if not items:
        return "Фильмов и сериалов пока нет."
    return "Кино:\n" + "\n".join(
        f"• {item.title} — {item.status}" for item in items
    )


def _format_lists(items: list[Any]) -> str:
    if not items:
        return "Списков пока нет."
    return "Списки:\n" + "\n".join(f"• {item.name}" for item in items)


def _format_trips(items: list[Any]) -> str:
    if not items:
        return "Путешествий пока нет."
    return "Путешествия:\n" + "\n".join(
        f"• {item.name} — {_format_date(item.start_date)}" for item in items
    )


def _format_wishlist(items: list[Any]) -> str:
    if not items:
        return "Вишлист пуст."
    return "Вишлист:\n" + "\n".join(
        f"• {item.title} — {item.status}" for item in items
    )


def _format_notes(items: list[Any]) -> str:
    if not items:
        return "Заметок пока нет."
    return "Заметки:\n" + "\n".join(f"• {item.title}" for item in items)


@router.message(lambda message: message.text in SECTION_LABELS)
async def show_section(message: Message, context: Context, session) -> None:
    if context.user_id is None:
        await message.answer("Не удалось определить пользователя.")
        return

    user_service = UserService(session)
    couple = await user_service._couple_service.get_user_couple(context.user_id)
    if couple is None:
        await message.answer("Сначала создайте пару или присоединитесь к ней.")
        return

    section = message.text
    if section == "Задачи":
        items = await TaskService(session).get_all_tasks(
            couple.id, context.user_id, limit=10
        )
        text = _format_tasks(items)
    elif section == "Кино":
        items = await MovieService(session).get_all_movies(
            couple.id, context.user_id, limit=10
        )
        text = _format_movies(items)
    elif section == "Списки":
        items = await ListService(session).get_all_lists(
            couple.id, context.user_id, limit=10
        )
        text = _format_lists(items)
    elif section == "Путешествия":
        items = await TripService(session).get_all_trips(
            couple.id, context.user_id, limit=10
        )
        text = _format_trips(items)
    elif section == "Вишлист":
        items = await WishlistService(session).get_all_items(
            couple.id, context.user_id, limit=10
        )
        text = _format_wishlist(items)
    elif section == "Заметки":
        items = await NoteService(session).get_all_notes(
            couple.id, context.user_id, limit=10
        )
        text = _format_notes(items)
    else:
        user_settings = await SettingsService(session).get_user_settings(
            context.user_id
        )
        couple_settings = await SettingsService(session).get_couple_settings(
            couple.id, context.user_id
        )
        text = (
            "Настройки:\n"
            f"Имя: {user_settings.get('display_name') or 'не указано'}\n"
            f"Часовой пояс: {user_settings.get('timezone') or 'не указан'}\n"
            f"Пара: {couple_settings.get('name') or 'не указана'}"
        )

    await message.answer(text)
