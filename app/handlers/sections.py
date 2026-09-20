import logging
from datetime import date, datetime
from typing import Any

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.challenge_service import ChallengeService
from app.services.list_service import ListService
from app.services.movie_service import MovieService
from app.services.note_service import NoteService
from app.services.settings_service import SettingsService
from app.services.task_service import TaskService
from app.services.trip_service import TripService
from app.services.wishlist_service import WishlistService
from app.utils.callbacks import (
    inline_keyboard,
    require_user_id,
)
from app.utils.context import Context

router = Router()
logger = logging.getLogger(__name__)
PAGE_SIZE = 10

SECTION_LABELS = {
    "Задачи",
    "Кино",
    "Списки",
    "Путешествия",
    "Вишлист",
    "Заметки",
    "Челленджи",
    "Настройки",
}


def _format_date(value: date | datetime | None) -> str:
    if value is None:
        return "без даты"
    return value.strftime("%d.%m.%Y")


def _format_tasks(items: list[Any]) -> str:
    if not items:
        return "Задач пока нет.\nНажми «Добавить задачу»."
    return "Задачи:\n" + "\n".join(
        f"• {item.title} — {item.status} (до {item.due_at or '-'})"
        for item in items
    )


def _format_movies(items: list[Any]) -> str:
    if not items:
        return "Фильмов и сериалов пока нет.\nНажми «Добавить»."
    return "Кино:\n" + "\n".join(
        f"• {item.title} — {item.status}" for item in items
    )


def _format_lists(items: list[Any]) -> str:
    if not items:
        return "Списков пока нет.\nНажми «Добавить список»."
    return "Списки:\n" + "\n".join(f"• {item.name}" for item in items)


def _format_trips(items: list[Any]) -> str:
    if not items:
        return "Путешествий пока нет.\nНажми «Добавить путешествие»."
    return "Путешествия:\n" + "\n".join(
        f"• {item.name} — {_format_date(item.start_date)}" for item in items
    )


def _format_wishlist(items: list[Any]) -> str:
    if not items:
        return "Вишлист пуст.\nНажми «Добавить»."
    return "Вишлист:\n" + "\n".join(
        f"• {item.title} — {item.status}" for item in items
    )


def _format_notes(items: list[Any]) -> str:
    if not items:
        return "Заметок пока нет.\nНажми «Добавить заметку»."
    return "Заметки:\n" + "\n".join(f"• {item.title}" for item in items)


def _format_challenges(items: list[Any]) -> str:
    if not items:
        return "Челленджей пока нет.\nНажми «Создать челлендж»."
    return "Челленджи:\n" + "\n".join(
        f"• {item.title} — {_format_date(item.start_date)}–{_format_date(item.end_date)}"
        for item in items
    )


def paginate(items: list[Any], page: int) -> tuple[list[Any], int, int]:
    page_count = max(1, (len(items) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(max(page, 0), page_count - 1)
    start = page * PAGE_SIZE
    return items[start : start + PAGE_SIZE], page, page_count


def pagination_row(prefix: str, page: int, page_count: int) -> list[tuple[str, str]]:
    row: list[tuple[str, str]] = []
    if page > 0:
        row.append(("Назад", f"{prefix}:{page - 1}"))
    if page + 1 < page_count:
        row.append(("Далее", f"{prefix}:{page + 1}"))
    return row


def _task_list_keyboard(
    items: list[Any], page: int = 0, page_count: int = 1
) -> Any:
    rows: list[list[tuple[str, str]]] = [[("Добавить задачу", "tasks:create")]]
    rows += [[(item.title, f"task:{item.id}")] for item in items]
    if nav := pagination_row("tasks:list", page, page_count):
        rows.append(nav)
    return inline_keyboard(rows)


def _movie_list_keyboard(
    items: list[Any], page: int = 0, page_count: int = 1
) -> Any:
    rows: list[list[tuple[str, str]]] = [[("Добавить", "movies:create")]]
    rows += [[(item.title, f"movie:{item.id}")] for item in items]
    if nav := pagination_row("movies:list", page, page_count):
        rows.append(nav)
    return inline_keyboard(rows)


def _list_list_keyboard(
    items: list[Any], page: int = 0, page_count: int = 1
) -> Any:
    rows: list[list[tuple[str, str]]] = [[("Добавить список", "lists:create")]]
    rows += [[(item.name, f"list:{item.id}")] for item in items]
    if nav := pagination_row("lists:list", page, page_count):
        rows.append(nav)
    return inline_keyboard(rows)


def _trip_list_keyboard(
    items: list[Any], page: int = 0, page_count: int = 1
) -> Any:
    rows: list[list[tuple[str, str]]] = [[("Добавить путешествие", "trips:create")]]
    rows += [[(item.name, f"trip:{item.id}")] for item in items]
    if nav := pagination_row("trips:list", page, page_count):
        rows.append(nav)
    return inline_keyboard(rows)


def _wishlist_list_keyboard(
    items: list[Any], page: int = 0, page_count: int = 1
) -> Any:
    rows: list[list[tuple[str, str]]] = [[("Добавить", "wishlist:create")]]
    rows += [[(item.title, f"wish:{item.id}")] for item in items]
    if nav := pagination_row("wishlist:list", page, page_count):
        rows.append(nav)
    return inline_keyboard(rows)


def _note_list_keyboard(
    items: list[Any], page: int = 0, page_count: int = 1
) -> Any:
    rows: list[list[tuple[str, str]]] = [[("Добавить заметку", "notes:create")]]
    rows += [[(item.title, f"note:{item.id}")] for item in items]
    if nav := pagination_row("notes:list", page, page_count):
        rows.append(nav)
    return inline_keyboard(rows)


def _challenge_list_keyboard(
    items: list[Any], page: int = 0, page_count: int = 1
) -> Any:
    rows: list[list[tuple[str, str]]] = [[("Создать челлендж", "challenges:create")]]
    rows += [[(item.title[:40], f"chl:{item.id}")] for item in items]
    if nav := pagination_row("challenges:list", page, page_count):
        rows.append(nav)
    return inline_keyboard(rows)


@router.message(lambda message: message.text in SECTION_LABELS)
async def show_section(message: Message, context: Context, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    user_id = require_user_id(context)
    try:
        from app.utils.callbacks import get_couple
        couple = await get_couple(session, user_id)
    except Exception as exc:  # noqa: BLE001
        await message.answer(str(exc) if hasattr(exc, "message") else "Ошибка доступа.")
        return

    section = message.text
    if section == "Задачи":
        all_items = await TaskService(session).get_all_tasks(couple.id, user_id)
        items, page, page_count = paginate(all_items, 0)
        await message.answer(
            _format_tasks(items),
            reply_markup=_task_list_keyboard(items, page, page_count),
        )
    elif section == "Кино":
        all_items = await MovieService(session).get_all_movies(couple.id, user_id)
        items, page, page_count = paginate(all_items, 0)
        await message.answer(
            _format_movies(items),
            reply_markup=_movie_list_keyboard(items, page, page_count),
        )
    elif section == "Списки":
        all_items = await ListService(session).get_all_lists(couple.id, user_id)
        items, page, page_count = paginate(all_items, 0)
        await message.answer(
            _format_lists(items),
            reply_markup=_list_list_keyboard(items, page, page_count),
        )
    elif section == "Путешествия":
        all_items = await TripService(session).get_all_trips(couple.id, user_id)
        items, page, page_count = paginate(all_items, 0)
        await message.answer(
            _format_trips(items),
            reply_markup=_trip_list_keyboard(items, page, page_count),
        )
    elif section == "Вишлист":
        all_items = await WishlistService(session).get_all_items(couple.id, user_id)
        items, page, page_count = paginate(all_items, 0)
        await message.answer(
            _format_wishlist(items),
            reply_markup=_wishlist_list_keyboard(items, page, page_count),
        )
    elif section == "Заметки":
        all_items = await NoteService(session).get_all_notes(couple.id, user_id)
        items, page, page_count = paginate(all_items, 0)
        await message.answer(
            _format_notes(items),
            reply_markup=_note_list_keyboard(items, page, page_count),
        )
    elif section == "Челленджи":
        all_items = await ChallengeService(session).list_challenges(couple.id, user_id)
        items, page, page_count = paginate(all_items, 0)
        await message.answer(
            _format_challenges(items),
            reply_markup=_challenge_list_keyboard(items, page, page_count),
        )
    else:
        user_settings = await SettingsService(session).get_user_settings(user_id)
        couple_settings = await SettingsService(session).get_couple_settings(couple.id, user_id)
        text = (
            "Настройки:\n"
            f"Имя: {user_settings.get('display_name') or 'не указано'}\n"
            f"Часовой пояс: {user_settings.get('timezone') or 'не указан'}\n"
            f"Пара: {couple_settings.get('name') or 'не указана'}"
        )
        await message.answer(
            text,
            reply_markup=inline_keyboard(
                [
                    [("Имя", "settings:display"), ("Часовой пояс", "settings:timezone")],
                    [("Имя пары", "settings:couple")],
                ]
            ),
        )
