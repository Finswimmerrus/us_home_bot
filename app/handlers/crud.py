from __future__ import annotations

import logging
from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.exc import IntegrityError

from app.exceptions import ValidationError
from app.handlers.fsm import (
    ChallengeAmountFSM,
    ChallengeCreateFSM,
    ChallengeEntryFSM,
    CoupleNameFSM,
    ListCreateFSM,
    ListItemCreateFSM,
    MovieCreateFSM,
    MovieEditFSM,
    MovieRatingFSM,
    NoteCreateFSM,
    NoteEditFSM,
    PlaceCreateFSM,
    SettingsDisplayFSM,
    SettingsTimezoneFSM,
    TaskCreateFSM,
    TaskEditFSM,
    TripCreateFSM,
    WishlistCreateFSM,
)
from app.handlers.sections import (
    _challenge_list_keyboard,
    _format_challenges,
    _format_lists,
    _format_movies,
    _format_notes,
    _format_tasks,
    _format_trips,
    _format_wishlist,
    _task_list_keyboard,
    paginate,
    pagination_row,
)
from app.handlers.start import MAIN_MENU
from app.repositories.users import CoupleMemberRepository, UserRepository
from app.services.challenge_service import ChallengeService
from app.services.couple_service import CoupleService
from app.services.list_service import ListService
from app.services.movie_service import VALID_MOVIE_STATUSES, MovieService
from app.services.note_service import NoteService
from app.services.settings_service import SettingsService
from app.services.task_service import VALID_PRIORITIES, TaskService
from app.services.trip_service import PlaceService, TripService
from app.services.wishlist_service import VALID_WISHLIST_STATUSES, WishlistService
from app.utils.callbacks import (
    CANCEL_BUTTON,
    SKIP_VALUES,
    alert_callback,
    back_to_menu_keyboard,
    callback_int,
    cancel_keyboard,
    get_couple,
    inline_keyboard,
    optional_keyboard,
    reply_callback,
    require_user_id,
)
from app.utils.context import Context

logger = logging.getLogger(__name__)
router = Router()

TASK_STATUS_TRANSITIONS: dict[str, list[str]] = {
    "TODO": ["IN_PROGRESS", "DONE", "CANCELLED"],
    "IN_PROGRESS": ["TODO", "DONE", "CANCELLED"],
    "DONE": ["TODO", "IN_PROGRESS"],
    "CANCELLED": ["TODO", "IN_PROGRESS"],
}
TASK_STATUS_LABEL = {
    "TODO": "К выполнению",
    "IN_PROGRESS": "В процессе",
    "DONE": "Готово",
    "CANCELLED": "Отменено",
}


async def _uc(context: Context, session: Any) -> tuple[Any, int]:
    user_id = require_user_id(context)
    couple = await get_couple(session, user_id)
    return couple, user_id


def _parse_datetime(text: str | None) -> datetime | None:
    text = (text or "").strip()
    for fmt in (
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M",
        "%d.%m.%Y %H:%M",
        "%Y-%m-%d",
        "%d.%m.%Y",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _parse_date(text: str | None) -> date | None:
    text = (text or "").strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _fmt_dt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    return value.strftime("%d.%m.%Y")


def _norm(text: str | None) -> str:
    return (text or "").strip()


def _callback_page(callback: CallbackQuery, prefix: str) -> int:
    data = callback.data or ""
    marker = f"{prefix}:"
    if not data.startswith(marker):
        return 0
    return max(callback_int(data.removeprefix(marker)), 0)


def _is_skip(text: str | None) -> bool:
    return _norm(text).lower() in SKIP_VALUES


def _priority_keyboard(callback_prefix: str) -> Any:
    return inline_keyboard(
        [
            [("Низкий", f"{callback_prefix}:LOW"), ("Обычный", f"{callback_prefix}:NORMAL")],
            [("Высокий", f"{callback_prefix}:HIGH")],
        ]
    )


def _task_text(task: Any) -> str:
    assignee = f" (назначена: {task.assigned_to})" if task.assigned_to else ""
    text = (
        f"📌 {task.title}\n"
        f"Статус: {task.status}\n"
        f"Приоритет: {task.priority}{assignee}\n"
        f"Дедлайн: {_fmt_dt(task.due_at)}\n"
        f"ID: {task.id}"
    )
    if task.description:
        text += f"\n\n{task.description}"
    return text


def _task_detail_markup(task: Any) -> Any:
    rows: list[list[tuple[str, str]]] = [
        [("Редактировать", f"task:edit:{task.id}")],
        [("Заголовок", f"task:field:{task.id}:title"),
         ("Описание", f"task:field:{task.id}:description")],
        [("Приоритет", f"task:field:{task.id}:priority"),
         ("Дедлайн", f"task:field:{task.id}:due_at")],
    ]
    for status in TASK_STATUS_TRANSITIONS.get(task.status, []):
        rows.append([(TASK_STATUS_LABEL[status], f"task:status:{task.id}:{status}")])
    rows.append([("Удалить", f"task:delete:{task.id}"), ("↩️ К задачам", "tasks:list")])
    return inline_keyboard(rows)


async def _cancel_flow(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.", reply_markup=MAIN_MENU)


@router.message(StateFilter("*"), Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await _cancel_flow(message, state)


@router.message(StateFilter("*"), lambda m: (m.text or "").strip().lower() == CANCEL_BUTTON.lower())
async def btn_cancel(message: Message, state: FSMContext) -> None:
    await _cancel_flow(message, state)


async def _task_by_callback(callback: CallbackQuery, context: Context, session: Any) -> tuple[Any, Any, int]:
    parts = callback.data.split(":")
    task_id = callback_int(parts[2] if len(parts) > 2 and parts[1] in {"edit", "delete"} else parts[1])
    couple, user_id = await _uc(context, session)
    task = await TaskService(session).get_task(couple.id, user_id, task_id)
    return task, couple, user_id


@router.callback_query(lambda c: c.data and c.data.startswith("tasks:list"))
async def cb_tasks_list(callback: CallbackQuery, context: Context, session: Any) -> None:
    couple, user_id = await _uc(context, session)
    all_items = await TaskService(session).get_all_tasks(couple.id, user_id)
    items, page, page_count = paginate(
        all_items, _callback_page(callback, "tasks:list")
    )
    await reply_callback(
        callback,
        _format_tasks(items),
        _task_list_keyboard(items, page, page_count),
    )


@router.callback_query(lambda c: c.data == "tasks:create")
async def cb_task_create_start(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    _, user_id = await _uc(context, session)
    await state.set_data({"flow": "task_create", "created_by": user_id})
    await state.set_state(TaskCreateFSM.title)
    await reply_callback(callback, "Введите название задачи:", cancel_keyboard())


@router.message(TaskCreateFSM.title)
async def msg_task_title(message: Message, state: FSMContext) -> None:
    text = _norm(message.text)
    if not text:
        await message.answer("Введите название задачи.")
        return
    await state.update_data(title=text)
    await state.set_state(TaskCreateFSM.description)
    await message.answer("Описание:", reply_markup=optional_keyboard())


@router.message(TaskCreateFSM.description)
async def msg_task_description(message: Message, state: FSMContext) -> None:
    description = None if _is_skip(message.text) else _norm(message.text)
    await state.update_data(description=description)
    await state.set_state(TaskCreateFSM.priority)
    await message.answer("Приоритет:", reply_markup=_priority_keyboard("task:create:priority"))


@router.callback_query(lambda c: c.data and c.data.startswith("task:create:priority:"))
async def cb_task_create_priority(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    priority = callback.data.split(":")[-1].upper()
    if priority not in VALID_PRIORITIES:
        await alert_callback(callback, "Недопустимый приоритет.")
        return
    await state.update_data(priority=priority)
    await state.set_state(TaskCreateFSM.assigned_to)
    user_id = require_user_id(context)
    couple = await get_couple(session, user_id)
    partner = await CoupleService(session).get_other_member(couple.id, user_id)
    await reply_callback(callback, "Кто выполняет?", _task_assignment_keyboard("task:create:assign", partner))


def _task_assignment_keyboard(callback_prefix: str, partner: Any | None = None) -> Any:
    rows: list[list[tuple[str, str]]] = [
        [("Мне", f"{callback_prefix}:self"), ("Не назначать", f"{callback_prefix}:none")],
    ]
    if partner is not None:
        name = partner.display_name or partner.first_name or partner.username or "Партнёру"
        rows.insert(1, [(name, f"{callback_prefix}:partner")])
    return inline_keyboard(rows)


@router.callback_query(lambda c: c.data and c.data.startswith("task:create:assign:"))
async def cb_task_create_assign(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    mode = callback.data.split(":")[-1]
    user_id = require_user_id(context)
    if mode == "self":
        assigned_to: int | None = user_id
    elif mode == "partner":
        couple = await get_couple(session, user_id)
        partner = await CoupleService(session).get_other_member(couple.id, user_id)
        if partner is None:
            await alert_callback(callback, "Партнёр не найден.")
            return
        assigned_to = partner.id
    elif mode == "none":
        assigned_to = None
    else:
        await alert_callback(callback, "Неверный выбор.")
        return
    await state.update_data(assigned_to=assigned_to)
    await state.set_state(TaskCreateFSM.due_at)
    await reply_callback(callback, "Введите дедлайн (дд.мм.гггг / гггг-мм-дд):", optional_keyboard())


@router.message(TaskCreateFSM.due_at)
async def msg_task_due_at(message: Message, state: FSMContext) -> None:
    text = message.text
    if _is_skip(text):
        due_at_raw = None
    else:
        due_at = _parse_datetime(text)
        if due_at is None:
            await message.answer(
                "Неверный формат даты/времени. Попробуйте снова или нажмите «Пропустить».",
                reply_markup=optional_keyboard(),
            )
            return
        due_at_raw = due_at.isoformat()
    await state.update_data(due_at=due_at_raw)
    data = await state.get_data()
    summary = _build_task_summary(data)
    await state.set_state(TaskCreateFSM.confirm)
    assigned_to = data.get("assigned_to")
    created_by = data.get("created_by")
    if assigned_to and assigned_to != created_by:
        rows = [
            [("➕ Создать и уведомить", "task:create:confirm:notify")],
            [("Без уведомления", "task:create:confirm:silent")],
            [("Отмена", "task:create:cancel")],
        ]
    else:
        rows = [
            [("➕ Создать задачу", "task:create:confirm:silent")],
            [("Отмена", "task:create:cancel")],
        ]
    await message.answer(summary, reply_markup=inline_keyboard(rows))


def _build_task_summary(data: dict) -> str:
    assigned = data.get("assigned_to")
    assigned_label = "не назначена"
    if assigned:
        assigned_label = f"id={assigned}"
    return (
        "✅ Новая задача\n"
        f"Название: {data.get('title')}\n"
        f"Описание: {data.get('description') or '-'}\n"
        f"Приоритет: {data.get('priority', 'NORMAL')}\n"
        f"Назначить: {assigned_label}\n"
        f"Дедлайн: {data.get('due_at') or '-'}"
    )


@router.callback_query(
    lambda c: c.data
    and c.data in {"task:create:confirm", "task:create:confirm:notify", "task:create:confirm:silent"}
)
async def cb_task_create_confirm(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("title"):
        await alert_callback(callback, "Название не задано.")
        return
    couple, user_id = await _uc(context, session)
    due_raw = data.get("due_at")
    due_at = datetime.fromisoformat(due_raw) if due_raw else None
    try:
        task = await TaskService(session).create_task(
            couple.id,
            user_id,
            _norm(data.get("title")),
            description=data.get("description"),
            priority=data.get("priority", "NORMAL"),
            assigned_to=data.get("assigned_to"),
            due_at=due_at,
        )
    except ValidationError as exc:
        await alert_callback(callback, exc.message)
        return
    except IntegrityError:
        await session.rollback()
        await alert_callback(callback, "Не удалось создать задачу.")
        return
    notification_failed = False
    should_notify = callback.data == "task:create:confirm:notify"
    if should_notify and task.assigned_to and task.assigned_to != user_id:
        assignee = await UserRepository(session).get_by_id(task.assigned_to)
        if assignee is not None:
            notification = f"Тебе назначена новая задача: {task.title}"
            if task.description:
                notification += f"\nОписание: {task.description}"
            if task.due_at:
                notification += f"\nДедлайн: {_fmt_dt(task.due_at)}"
            try:
                await callback.bot.send_message(assignee.telegram_id, notification)
            except TelegramAPIError:
                notification_failed = True
                logger.exception("Failed to notify assignee for task id=%s", task.id)
    await state.clear()
    result_text = f"Задача создана: {task.title}"
    if should_notify:
        result_text += (
            "\nНе удалось отправить уведомление."
            if notification_failed
            else "\nИсполнитель получил уведомление."
        )
    await reply_callback(callback, result_text, _task_detail_markup(task))


@router.callback_query(lambda c: c.data == "task:create:cancel")
async def cb_task_create_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await reply_callback(callback, "Отменено.", MAIN_MENU)


@router.callback_query(lambda c: c.data and c.data.startswith("task:") and c.data.split(":")[1].isdigit())
async def cb_task_detail(callback: CallbackQuery, context: Context, session: Any) -> None:
    task, _, _ = await _task_by_callback(callback, context, session)
    await reply_callback(callback, _task_text(task), _task_detail_markup(task))


@router.callback_query(lambda c: c.data and c.data.startswith("task:edit:"))
async def cb_task_edit(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    task, _, _ = await _task_by_callback(callback, context, session)
    await state.set_data({"flow": "task_edit", "item_id": task.id})
    await state.set_state(TaskEditFSM.value)
    await reply_callback(
        callback,
        "Введите новое значение:",
        inline_keyboard(
            [
                [("Заголовок", f"task:field:{task.id}:title"),
                 ("Описание", f"task:field:{task.id}:description")],
                [("Приоритет", f"task:field:{task.id}:priority"),
                 ("Дедлайн", f"task:field:{task.id}:due_at")],
                [("↩️ Назад", f"task:{task.id}")],
            ]
        ),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("task:field:") and c.data.split(":")[3] in ("title", "description", "due_at"))
async def cb_task_field(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    field = parts[3]
    await state.update_data(item_id=callback_int(parts[2]), field=field)
    await state.set_state(TaskEditFSM.value)
    prompt = {
        "title": "Введите новое название:",
        "description": "Введите новое описание:",
        "due_at": "Введите дедлайн или нажмите «Пропустить», чтобы оставить без изменений:",
    }[field]
    keyboard = optional_keyboard() if field in {"description", "due_at"} else cancel_keyboard()
    await reply_callback(callback, prompt, keyboard)


@router.callback_query(lambda c: c.data and c.data.startswith("task:field:") and c.data.split(":")[3] == "priority")
async def cb_task_priority_edit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(field="priority")
    await reply_callback(callback, "Выберите приоритет:", _priority_keyboard(f"task:priority_edit:{callback.data.split(':')[2]}"))


@router.callback_query(lambda c: c.data and c.data.startswith("task:priority_edit:"))
async def cb_task_priority_confirm(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    parts = callback.data.split(":")
    task_id = callback_int(parts[2])
    priority = parts[-1].upper()
    if priority not in VALID_PRIORITIES:
        await alert_callback(callback, "Недопустимый приоритет.")
        return
    couple, user_id = await _uc(context, session)
    task = await TaskService(session).update_task(couple.id, user_id, task_id, priority=priority)
    await state.clear()
    await reply_callback(callback, _task_text(task), _task_detail_markup(task))


@router.message(TaskEditFSM.value)
async def msg_task_edit_value(message: Message, context: Context, session: Any, state: FSMContext) -> None:
    data = await state.get_data()
    field = data.get("field")
    task_id = callback_int(data.get("item_id"))
    text = _norm(message.text)
    couple, user_id = await _uc(context, session)
    service = TaskService(session)
    if field == "title":
        if not text:
            await message.answer("Введите название.")
            return
        task = await service.update_task(couple.id, user_id, task_id, title=text)
    elif field == "description":
        desc = None if _is_skip(text) else text
        task = await service.update_task(couple.id, user_id, task_id, description=desc)
    elif field == "due_at":
        if _is_skip(text):
            task = await service.get_task(couple.id, user_id, task_id)
        else:
            due_at = _parse_datetime(text)
            if due_at is None:
                await message.answer(
                    "Неверный формат даты. Попробуйте снова или нажмите «Пропустить».",
                    reply_markup=optional_keyboard(),
                )
                return
            task = await service.update_task(couple.id, user_id, task_id, due_at=due_at)
    else:
        await message.answer("Неизвестное поле.")
        return
    await state.clear()
    await message.answer(_task_text(task), reply_markup=_task_detail_markup(task))


@router.callback_query(lambda c: c.data and c.data.startswith("task:status:"))
async def cb_task_status(callback: CallbackQuery, context: Context, session: Any) -> None:
    parts = callback.data.split(":")
    task_id = callback_int(parts[2])
    new_status = parts[-1]
    couple, user_id = await _uc(context, session)
    task = await TaskService(session).change_status(couple.id, user_id, task_id, new_status)
    await reply_callback(callback, _task_text(task), _task_detail_markup(task))


@router.callback_query(lambda c: c.data and c.data.startswith("task:delete:"))
async def cb_task_delete(callback: CallbackQuery, context: Context, session: Any) -> None:
    task_id = callback_int(callback.data.split(":")[2])
    couple, user_id = await _uc(context, session)
    await TaskService(session).delete_task(couple.id, user_id, task_id)
    await reply_callback(callback, "Задача удалена.", back_to_menu_keyboard())


async def _movie_by_callback(callback: CallbackQuery, context: Context, session: Any) -> tuple[Any, Any, int]:
    parts = callback.data.split(":")
    movie_id = callback_int(parts[2] if len(parts) > 2 and parts[1] in {"edit", "delete", "rate"} else parts[1])
    couple, user_id = await _uc(context, session)
    movie = await MovieService(session).get_movie(couple.id, user_id, movie_id)
    return movie, couple, user_id


def _movie_text(movie: Any) -> str:
    watched = _fmt_dt(movie.watched_at) if getattr(movie, "watched_at", None) else "-"
    text = (
        f"🎬 {movie.title} [{movie.status}]\n"
        f"Жанр: {movie.type}\nПросмотр: {watched}\nID: {movie.id}"
    )
    if movie.description:
        text += f"\n\n{movie.description}"
    return text


def _movie_markup(movie: Any) -> Any:
    rows: list[list[tuple[str, str]]] = [
        [("Редактировать", f"movie:edit:{movie.id}")],
        [("🔄 Изменить статус", f"movie:status_menu:{movie.id}")],
        [("⭐ Оценить", f"movie:rate:{movie.id}")],
    ]
    for status in VALID_MOVIE_STATUSES:
        if status != movie.status:
            rows.append([(status, f"movie:status:{movie.id}:{status}")])
    rows.append([("Удалить", f"movie:delete:{movie.id}"), ("↩️ К кино", "movies:list")])
    return inline_keyboard(rows)


@router.callback_query(lambda c: c.data and c.data.startswith("movies:list"))
async def cb_movies_list(callback: CallbackQuery, context: Context, session: Any) -> None:
    couple, user_id = await _uc(context, session)
    all_items = await MovieService(session).get_all_movies(couple.id, user_id)
    items, page, page_count = paginate(
        all_items, _callback_page(callback, "movies:list")
    )
    await reply_callback(
        callback,
        _format_movies(items),
        _movie_list_keyboard(items, page, page_count),
    )


def _movie_list_keyboard(
    items: list[Any], page: int = 0, page_count: int = 1
) -> Any:
    rows: list[list[tuple[str, str]]] = [[(item.title, f"movie:{item.id}")] for item in items]
    if nav := pagination_row("movies:list", page, page_count):
        rows.append(nav)
    rows.append([("➕ Новый фильм", "movies:create")])
    return inline_keyboard(rows)


@router.callback_query(lambda c: c.data == "movies:create")
async def cb_movie_create_start(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    await _uc(context, session)
    await state.set_data({"flow": "movie_create"})
    await state.set_state(MovieCreateFSM.title)
    await reply_callback(callback, "Введите название фильма/сериала:", cancel_keyboard())


@router.message(MovieCreateFSM.title)
async def msg_movie_title(message: Message, state: FSMContext) -> None:
    text = _norm(message.text)
    if not text:
        await message.answer("Введите название.")
        return
    await state.update_data(title=text)
    await state.set_state(MovieCreateFSM.description)
    await message.answer("Описание:", reply_markup=optional_keyboard())


@router.message(MovieCreateFSM.description)
async def msg_movie_description(message: Message, context: Context, session: Any, state: FSMContext) -> None:
    data = await state.get_data()
    couple, user_id = await _uc(context, session)
    description = None if _is_skip(message.text) else _norm(message.text)
    try:
        movie = await MovieService(session).add_movie(
            couple.id, user_id, _norm(data.get("title")), description=description
        )
    except ValidationError as exc:
        await message.answer(exc.message)
        return
    await state.clear()
    await message.answer(f"Фильм добавлен: {movie.title}", reply_markup=_movie_markup(movie))


@router.callback_query(lambda c: c.data and c.data.startswith("movie:") and c.data.split(":")[1].isdigit())
async def cb_movie_detail(callback: CallbackQuery, context: Context, session: Any) -> None:
    movie, _, _ = await _movie_by_callback(callback, context, session)
    await reply_callback(callback, _movie_text(movie), _movie_markup(movie))


@router.callback_query(lambda c: c.data and c.data.startswith("movie:edit:"))
async def cb_movie_edit(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    movie, _, _ = await _movie_by_callback(callback, context, session)
    await state.set_data({"flow": "movie_edit", "item_id": movie.id})
    await state.set_state(MovieEditFSM.value)
    await reply_callback(callback, "Введите новое значение:", _movie_edit_keyboard(movie.id))


def _movie_edit_keyboard(movie_id: int) -> Any:
    return inline_keyboard(
        [
            [("Заголовок", f"movie:field:{movie_id}:title"),
             ("Описание", f"movie:field:{movie_id}:description")],
            [("↩️ Назад", f"movie:{movie_id}")],
        ]
    )


@router.callback_query(lambda c: c.data and c.data.startswith("movie:field:"))
async def cb_movie_field(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    await state.update_data(item_id=callback_int(parts[2]), field=parts[3])
    await state.set_state(MovieEditFSM.value)
    prompt = "Введите новое название:" if parts[3] == "title" else "Введите новое описание:"
    keyboard = optional_keyboard() if parts[3] == "description" else cancel_keyboard()
    await reply_callback(callback, prompt, keyboard)


@router.message(MovieEditFSM.value)
async def msg_movie_edit_value(message: Message, context: Context, session: Any, state: FSMContext) -> None:
    data = await state.get_data()
    field = data.get("field")
    movie_id = callback_int(data.get("item_id"))
    text = _norm(message.text)
    couple, user_id = await _uc(context, session)
    service = MovieService(session)
    movie = await service.get_movie(couple.id, user_id, movie_id)
    try:
        if field == "title":
            if not text:
                await message.answer("Введите название.")
                return
            await service.update_movie(couple.id, user_id, movie_id, title=text)
        elif field == "description":
            await service.update_movie(couple.id, user_id, movie_id, description=(None if _is_skip(text) else text))
        else:
            await message.answer("Неизвестное поле.")
            return
    except ValidationError as exc:
        await message.answer(exc.message)
        return
    await state.clear()
    movie = await service.get_movie(couple.id, user_id, movie_id)
    await message.answer(_movie_text(movie), reply_markup=_movie_markup(movie))


@router.callback_query(lambda c: c.data and c.data.startswith("movie:status:"))
async def cb_movie_status(callback: CallbackQuery, context: Context, session: Any) -> None:
    parts = callback.data.split(":")
    movie_id = callback_int(parts[2])
    new_status = parts[-1]
    couple, user_id = await _uc(context, session)
    movie = await MovieService(session).change_status(couple.id, user_id, movie_id, new_status)
    await reply_callback(callback, _movie_text(movie), _movie_markup(movie))


@router.callback_query(lambda c: c.data and c.data.startswith("movie:status_menu:"))
async def cb_movie_status_menu(callback: CallbackQuery, context: Context, session: Any) -> None:
    movie_id = callback_int(callback.data.split(":")[2])
    couple, user_id = await _uc(context, session)
    movie = await MovieService(session).get_movie(couple.id, user_id, movie_id)
    rows = [
        [(status, f"movie:status:{movie.id}:{status}")]
        for status in VALID_MOVIE_STATUSES
        if status != movie.status
    ]
    rows.append([("↩️ Назад", f"movie:{movie.id}")])
    await reply_callback(callback, "Выберите новый статус:", inline_keyboard(rows))


@router.callback_query(lambda c: c.data and c.data.startswith("movie:rate:"))
async def cb_movie_rate(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    await state.set_data({"flow": "movie_rate", "item_id": callback_int(callback.data.split(":")[2])})
    await state.set_state(MovieRatingFSM.rating)
    await reply_callback(callback, "Введите оценку от 1 до 5:", cancel_keyboard())


@router.message(MovieRatingFSM.rating)
async def msg_movie_rating(message: Message, context: Context, session: Any, state: FSMContext) -> None:
    data = await state.get_data()
    movie_id = callback_int(data.get("item_id"))
    text = _norm(message.text)
    try:
        rating = int(text)
    except ValueError:
        await message.answer("Введите число от 1 до 5.")
        return
    if not 1 <= rating <= 5:
        await message.answer("Оценка должна быть от 1 до 5.")
        return
    couple, user_id = await _uc(context, session)
    try:
        await MovieService(session).rate_movie(couple.id, user_id, movie_id, rating)
    except ValidationError as exc:
        await message.answer(exc.message)
        return
    movie = await MovieService(session).get_movie(couple.id, user_id, movie_id)
    await state.clear()
    await message.answer(_movie_text(movie), reply_markup=_movie_markup(movie))


@router.callback_query(lambda c: c.data and c.data.startswith("movie:delete:"))
async def cb_movie_delete(callback: CallbackQuery, context: Context, session: Any) -> None:
    movie_id = callback_int(callback.data.split(":")[2])
    couple, user_id = await _uc(context, session)
    await MovieService(session).delete_movie(couple.id, user_id, movie_id)
    await reply_callback(callback, "Фильм удалён.", back_to_menu_keyboard())


async def _list_by_callback(callback: CallbackQuery, context: Context, session: Any) -> tuple[Any, Any, int]:
    list_id = callback_int(callback.data.split(":")[1])
    couple, user_id = await _uc(context, session)
    lst = await ListService(session).get_list(couple.id, user_id, list_id)
    return lst, couple, user_id


@router.callback_query(lambda c: c.data and c.data.startswith("lists:list"))
async def cb_lists_list(callback: CallbackQuery, context: Context, session: Any) -> None:
    couple, user_id = await _uc(context, session)
    all_items = await ListService(session).get_all_lists(couple.id, user_id)
    items, page, page_count = paginate(
        all_items, _callback_page(callback, "lists:list")
    )
    await reply_callback(
        callback,
        _format_lists(items),
        _list_list_keyboard(items, page, page_count),
    )


def _list_list_keyboard(
    items: list[Any], page: int = 0, page_count: int = 1
) -> Any:
    rows: list[list[tuple[str, str]]] = [[(item.name, f"list:{item.id}")] for item in items]
    if nav := pagination_row("lists:list", page, page_count):
        rows.append(nav)
    rows.append([("➕ Новый список", "lists:create")])
    return inline_keyboard(rows)


@router.callback_query(lambda c: c.data == "lists:create")
async def cb_list_create_start(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    await _uc(context, session)
    await state.set_state(ListCreateFSM.name)
    await reply_callback(callback, "Введите название списка:", cancel_keyboard())


@router.message(ListCreateFSM.name)
async def msg_list_name(message: Message, context: Context, session: Any, state: FSMContext) -> None:
    name = _norm(message.text)
    if not name:
        await message.answer("Введите название списка.")
        return
    couple, user_id = await _uc(context, session)
    try:
        lst = await ListService(session).create_list(couple.id, user_id, name)
    except ValidationError as exc:
        await message.answer(exc.message)
        return
    except IntegrityError:
        await session.rollback()
        await message.answer("Список с таким названием уже существует.", reply_markup=MAIN_MENU)
        await state.clear()
        return
    await state.clear()
    await message.answer(f"Список «{lst.name}» создан.", reply_markup=_list_detail_markup(lst))
    await _render_list(callback_message=message, lst=lst, session=session, couple_id=couple.id, user_id=user_id)


async def _render_list(callback_message: Any, lst: Any, session: Any, couple_id: int, user_id: int) -> None:
    items = await ListService(session).get_items(couple_id, user_id, lst.id, include_completed=True)
    text = f"Список «{lst.name}»:\n" + "\n".join(f"• {i.title}" for i in items)
    await callback_message.answer(text, reply_markup=_list_detail_markup(lst))


def _list_detail_markup(lst: Any) -> Any:
    rows: list[list[tuple[str, str]]] = [
        [("➕ Новый пункт", f"list:item:add:{lst.id}")],
    ]
    rows += [[(item.title, f"list:item:{item.id}")] for item in getattr(lst, "items", [])]
    rows.append([("Удалить список", f"list:delete:{lst.id}"), ("↩️ К спискам", "lists:list")])
    return inline_keyboard(rows)


@router.callback_query(lambda c: c.data and c.data.startswith("list:") and c.data.split(":")[1].isdigit())
async def cb_list_detail(callback: CallbackQuery, context: Context, session: Any) -> None:
    lst, couple, user_id = await _list_by_callback(callback, context, session)
    await reply_callback(callback, f"Список «{lst.name}»", _list_detail_markup(lst))


@router.callback_query(lambda c: c.data and c.data.startswith("list:item:add:"))
async def cb_list_item_add(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    list_id = callback_int(callback.data.split(":")[3])
    await _uc(context, session)
    await state.set_data({"flow": "list_item_create", "list_id": list_id})
    await state.set_state(ListItemCreateFSM.title)
    await reply_callback(callback, "Введите название пункта:", cancel_keyboard())


@router.message(ListItemCreateFSM.title)
async def msg_list_item_title(message: Message, context: Context, session: Any, state: FSMContext) -> None:
    title = _norm(message.text)
    if not title:
        await message.answer("Введите название пункта.")
        return
    data = await state.get_data()
    list_id = callback_int(data.get("list_id"))
    couple, user_id = await _uc(context, session)
    try:
        item = await ListService(session).add_item(couple.id, user_id, list_id, title)
    except ValidationError as exc:
        await message.answer(exc.message)
        return
    await state.clear()
    lst = await ListService(session).get_list(couple.id, user_id, list_id)
    await message.answer(f"Пункт «{item.title}» добавлен.", reply_markup=_list_item_detail_markup(lst, item))


def _list_item_detail_markup(lst: Any, item: Any) -> Any:
    return inline_keyboard(
        [
            [("Выполнить/Отменить", f"list:item:toggle:{item.id}"),
             ("Удалить", f"list:item:delete:{item.id}")],
            [("↩️ К списку", f"list:{lst.id}")],
        ]
    )


@router.callback_query(lambda c: c.data and c.data.startswith("list:item:") and c.data.split(":")[2] == "toggle")
async def cb_list_item_toggle(callback: CallbackQuery, context: Context, session: Any) -> None:
    item_id = callback_int(callback.data.split(":")[3])
    couple, user_id = await _uc(context, session)
    service = ListService(session)
    item = await service._item_repo.get_by_id(item_id)  # bypass; use item service? no direct method
    if item is None:
        await alert_callback(callback, "Пункт не найден.")
        return
    if item.completed_at is None:
        await service.complete_item(couple.id, user_id, item.list_id, item_id)
    else:
        await service.uncomplete_item(couple.id, user_id, item.list_id, item_id)
    lst = await service.get_list(couple.id, user_id, item.list_id)
    item = await service._item_repo.get_by_id(item_id)
    await reply_callback(callback, _item_text(item), _list_detail_markup(lst))


def _item_text(item: Any) -> str:
    status = "✅" if item.completed_at else "☐"
    return f"{status} {item.title}"


@router.callback_query(lambda c: c.data and c.data.startswith("list:item:") and c.data.split(":")[2].isdigit())
async def cb_list_item_detail(callback: CallbackQuery, context: Context, session: Any) -> None:
    item_id = callback_int(callback.data.split(":")[2])
    couple, user_id = await _uc(context, session)
    service = ListService(session)
    item = await service._item_repo.get_by_id(item_id)
    if item is None:
        await alert_callback(callback, "Пункт не найден.")
        return
    lst = await service.get_list(couple.id, user_id, item.list_id)
    await reply_callback(callback, _item_text(item), _list_item_detail_markup(lst, item))


@router.callback_query(lambda c: c.data and c.data.startswith("list:item:delete:"))
async def cb_list_item_delete(callback: CallbackQuery, context: Context, session: Any) -> None:
    item_id = callback_int(callback.data.split(":")[3])
    couple, user_id = await _uc(context, session)
    service = ListService(session)
    item = await service._item_repo.get_by_id(item_id)
    if item is None:
        await alert_callback(callback, "Пункт не найден.")
        return
    await service.delete_item(couple.id, user_id, item.list_id, item_id)
    lst = await service.get_list(couple.id, user_id, item.list_id)
    await reply_callback(callback, "Пункт удалён.", _list_detail_markup(lst))


@router.callback_query(lambda c: c.data and c.data.startswith("list:delete:"))
async def cb_list_delete(callback: CallbackQuery, context: Context, session: Any) -> None:
    list_id = callback_int(callback.data.split(":")[2])
    couple, user_id = await _uc(context, session)
    await ListService(session).delete_list(couple.id, user_id, list_id)
    await reply_callback(callback, "Список удалён.", back_to_menu_keyboard())


async def _trip_by_callback(callback: CallbackQuery, context: Context, session: Any) -> tuple[Any, Any, int]:
    trip_id = callback_int(callback.data.split(":")[1])
    couple, user_id = await _uc(context, session)
    trip = await TripService(session).get_trip(couple.id, user_id, trip_id)
    return trip, couple, user_id


def _trip_text(trip: Any) -> str:
    lines = [f"✈️ {trip.name}"]
    if trip.description:
        lines.append(trip.description)
    lines.append(f"Даты: {_fmt_dt(trip.start_date)} — {_fmt_dt(trip.end_date)}")
    lines.append(f"ID: {trip.id}")
    return "\n".join(lines)


def _trip_detail_markup(trip: Any) -> Any:
    rows: list[list[tuple[str, str]]] = [
        [("➕ Новое место", f"trip:place:add:{trip.id}")],
    ]
    for place in getattr(trip, "places", []):
        rows.append([(place.name, f"trip:place:{place.id}")])
    rows.append([("Удалить путешествие", f"trip:delete:{trip.id}"), ("↩️ К путешествиям", "trips:list")])
    return inline_keyboard(rows)


def _place_text(place: Any) -> str:
    lines = [f"📍 {place.name}"]
    if place.description:
        lines.append(place.description)
    if place.address:
        lines.append(f"Адрес: {place.address}")
    if place.url:
        lines.append(f"Ссылка: {place.url}")
    if place.visit_date:
        lines.append(f"Дата: {_fmt_dt(place.visit_date)}")
    lines.append(f"ID: {place.id}")
    return "\n".join(lines)


def _place_detail_markup(place: Any) -> Any:
    return inline_keyboard(
        [
            [("Удалить место", f"trip:place:delete:{place.id}")],
            [("↩️ К путешествию", f"trip:{place.trip_id}")],
        ]
    )


@router.callback_query(lambda c: c.data and c.data.startswith("trips:list"))
async def cb_trips_list(callback: CallbackQuery, context: Context, session: Any) -> None:
    couple, user_id = await _uc(context, session)
    all_items = await TripService(session).get_all_trips(couple.id, user_id)
    items, page, page_count = paginate(
        all_items, _callback_page(callback, "trips:list")
    )
    rows = [[(i.name, f"trip:{i.id}")] for i in items]
    if nav := pagination_row("trips:list", page, page_count):
        rows.append(nav)
    rows.append([("➕ Новое путешествие", "trips:create")])
    await reply_callback(callback, _format_trips(items), inline_keyboard(rows))


@router.callback_query(lambda c: c.data == "trips:create")
async def cb_trip_create_start(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    await _uc(context, session)
    await state.set_state(TripCreateFSM.title)
    await reply_callback(callback, "Введите название путешествия:", cancel_keyboard())


@router.message(TripCreateFSM.title)
async def msg_trip_title(message: Message, state: FSMContext) -> None:
    text = _norm(message.text)
    if not text:
        await message.answer("Введите название путешествия.")
        return
    await state.update_data(title=text)
    await state.set_state(TripCreateFSM.description)
    await message.answer("Описание:", reply_markup=optional_keyboard())


@router.message(TripCreateFSM.description)
async def msg_trip_description(message: Message, context: Context, session: Any, state: FSMContext) -> None:
    data = await state.get_data()
    couple, user_id = await _uc(context, session)
    description = None if _is_skip(message.text) else _norm(message.text)
    trip = await TripService(session).create_trip(
        couple.id, user_id, _norm(data.get("title")), description=description
    )
    await state.clear()
    await message.answer(f"Путешествие «{trip.name}» создано.", reply_markup=_trip_detail_markup(trip))


@router.callback_query(lambda c: c.data and c.data.startswith("trip:") and c.data.split(":")[1].isdigit())
async def cb_trip_detail(callback: CallbackQuery, context: Context, session: Any) -> None:
    trip, _, _ = await _trip_by_callback(callback, context, session)
    await reply_callback(callback, _trip_text(trip), _trip_detail_markup(trip))


@router.callback_query(lambda c: c.data and c.data.startswith("trip:place:add:"))
async def cb_trip_place_add(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    trip_id = callback_int(callback.data.split(":")[3])
    await _uc(context, session)
    await state.set_data({"flow": "place_create", "trip_id": trip_id})
    await state.set_state(PlaceCreateFSM.title)
    await reply_callback(callback, "Введите название места:", cancel_keyboard())


@router.callback_query(lambda c: c.data and c.data.startswith("trip:place:") and c.data.split(":")[2].isdigit())
async def cb_trip_place_detail(callback: CallbackQuery, context: Context, session: Any) -> None:
    place_id = callback_int(callback.data.split(":")[2])
    couple, user_id = await _uc(context, session)
    trip_id = await _trip_id_from_place(session, place_id)
    place = await PlaceService(session).get_place(couple.id, user_id, trip_id, place_id)
    await reply_callback(callback, _place_text(place), _place_detail_markup(place))


@router.message(PlaceCreateFSM.title)
async def msg_place_title(message: Message, state: FSMContext) -> None:
    text = _norm(message.text)
    if not text:
        await message.answer("Введите название места.")
        return
    await state.update_data(name=text)
    await state.set_state(PlaceCreateFSM.description)
    await message.answer("Описание:", reply_markup=optional_keyboard())


@router.message(PlaceCreateFSM.description)
async def msg_place_description(message: Message, context: Context, session: Any, state: FSMContext) -> None:
    data = await state.get_data()
    couple, user_id = await _uc(context, session)
    trip_id = callback_int(data.get("trip_id"))
    description = None if _is_skip(message.text) else _norm(message.text)
    place = await PlaceService(session).add_place(
        couple.id, user_id, trip_id, _norm(data.get("name")), description=description
    )
    await state.clear()
    trip = await TripService(session).get_trip(couple.id, user_id, trip_id)
    await message.answer(f"Место «{place.name}» добавлено.", reply_markup=_trip_detail_markup(trip))


@router.callback_query(lambda c: c.data and c.data.startswith("trip:place:delete:"))
async def cb_trip_place_delete(callback: CallbackQuery, context: Context, session: Any) -> None:
    place_id = callback_int(callback.data.split(":")[3])
    couple, user_id = await _uc(context, session)
    trip_id = await _trip_id_from_place(session, place_id)
    await PlaceService(session).delete_place(couple.id, user_id, trip_id, place_id)
    trip = await TripService(session).get_trip(couple.id, user_id, trip_id)
    await reply_callback(callback, "Место удалено.", _trip_detail_markup(trip))


async def _trip_id_from_place(session: Any, place_id: int) -> int:
    place = await PlaceService(session)._place_repo.get_by_id(place_id)
    if place is None:
        raise ValidationError("Место не найдено", field="place_id")
    return place.trip_id


@router.callback_query(lambda c: c.data and c.data.startswith("trip:delete:"))
async def cb_trip_delete(callback: CallbackQuery, context: Context, session: Any) -> None:
    trip_id = callback_int(callback.data.split(":")[2])
    couple, user_id = await _uc(context, session)
    await TripService(session).delete_trip(couple.id, user_id, trip_id)
    await reply_callback(callback, "Путешествие удалено.", back_to_menu_keyboard())


async def _wish_by_callback(callback, context, session):
    item_id = callback_int(callback.data.split(":")[1])
    couple, user_id = await _uc(context, session)
    item = await WishlistService(session).get_item(couple.id, user_id, item_id)
    return item, couple, user_id


def _wish_text(item: Any) -> str:
    price = f" {item.price}₽" if getattr(item, "price", None) else ""
    lines = [f"🎁 {item.title} [{item.status}]{price}"]
    if item.description:
        lines.append(item.description)
    if item.url:
        lines.append(f"Ссылка: {item.url}")
    lines.append(f"ID: {item.id}")
    return "\n".join(lines)


def _wish_markup(item: Any) -> Any:
    rows: list[list[tuple[str, str]]] = []
    for status in VALID_WISHLIST_STATUSES:
        if status != item.status:
            rows.append([(status, f"wish:status:{item.id}:{status}")])
    rows.append([("Удалить", f"wish:delete:{item.id}"), ("↩️ К вишлисту", "wishlist:list")])
    return inline_keyboard(rows)


@router.callback_query(lambda c: c.data and c.data.startswith("wishlist:list"))
async def cb_wishlist_list(callback: CallbackQuery, context: Context, session: Any) -> None:
    couple, user_id = await _uc(context, session)
    all_items = await WishlistService(session).get_all_items(couple.id, user_id)
    items, page, page_count = paginate(
        all_items, _callback_page(callback, "wishlist:list")
    )
    rows: list[list[tuple[str, str]]] = [[(item.title, f"wish:{item.id}")] for item in items]
    if nav := pagination_row("wishlist:list", page, page_count):
        rows.append(nav)
    rows.append([("➕ Новое желание", "wishlist:create")])
    await reply_callback(callback, _format_wishlist(items), inline_keyboard(rows))


@router.callback_query(lambda c: c.data == "wishlist:create")
async def cb_wishlist_create_start(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    await _uc(context, session)
    await state.set_state(WishlistCreateFSM.title)
    await reply_callback(callback, "Введите название вишлиста:", cancel_keyboard())


@router.message(WishlistCreateFSM.title)
async def msg_wishlist_title(message: Message, state: FSMContext) -> None:
    text = _norm(message.text)
    if not text:
        await message.answer("Введите название.")
        return
    await state.update_data(title=text)
    await state.set_state(WishlistCreateFSM.url)
    await message.answer("URL:", reply_markup=optional_keyboard())


@router.message(WishlistCreateFSM.url)
async def msg_wishlist_url(message: Message, context: Context, session: Any, state: FSMContext) -> None:
    data = await state.get_data()
    couple, user_id = await _uc(context, session)
    url = None if _is_skip(message.text) else _norm(message.text)
    try:
        item = await WishlistService(session).add_item(
            couple.id, user_id, _norm(data.get("title")), url=url
        )
    except ValidationError as exc:
        await message.answer(exc.message)
        return
    await state.clear()
    await message.answer(f"Добавлено: {item.title}", reply_markup=_wish_markup(item))


@router.callback_query(lambda c: c.data and c.data.startswith("wish:") and c.data.split(":")[1].isdigit())
async def cb_wish_detail(callback: CallbackQuery, context: Context, session: Any) -> None:
    item, _, _ = await _wish_by_callback(callback, context, session)
    await reply_callback(callback, _wish_text(item), _wish_markup(item))


@router.callback_query(lambda c: c.data and c.data.startswith("wish:status:"))
async def cb_wish_status(callback: CallbackQuery, context: Context, session: Any) -> None:
    parts = callback.data.split(":")
    item_id = callback_int(parts[2])
    new_status = parts[-1]
    couple, user_id = await _uc(context, session)
    item = await WishlistService(session).change_status(couple.id, user_id, item_id, new_status)
    await reply_callback(callback, _wish_text(item), _wish_markup(item))


@router.callback_query(lambda c: c.data and c.data.startswith("wish:delete:"))
async def cb_wish_delete(callback: CallbackQuery, context: Context, session: Any) -> None:
    item_id = callback_int(callback.data.split(":")[2])
    couple, user_id = await _uc(context, session)
    await WishlistService(session).delete_item(couple.id, user_id, item_id)
    await reply_callback(callback, "Удалено.", back_to_menu_keyboard())


async def _note_by_callback(callback, context, session):
    parts = callback.data.split(":")
    note_id = callback_int(parts[2] if len(parts) > 2 and parts[1] in {"edit", "delete"} else parts[1])
    couple, user_id = await _uc(context, session)
    note = await NoteService(session).get_note(couple.id, user_id, note_id)
    return note, couple, user_id


def _note_markup(note: Any) -> Any:
    return inline_keyboard(
        [
            [("Редактировать", f"note:edit:{note.id}")],
            [("Удалить", f"note:delete:{note.id}"), ("↩️ К заметкам", "notes:list")],
        ]
    )


@router.callback_query(lambda c: c.data and c.data.startswith("notes:list"))
async def cb_notes_list(callback: CallbackQuery, context: Context, session: Any) -> None:
    couple, user_id = await _uc(context, session)
    all_items = await NoteService(session).get_all_notes(couple.id, user_id)
    items, page, page_count = paginate(
        all_items, _callback_page(callback, "notes:list")
    )
    rows: list[list[tuple[str, str]]] = [[(item.title, f"note:{item.id}")] for item in items]
    if nav := pagination_row("notes:list", page, page_count):
        rows.append(nav)
    rows.append([("➕ Новая заметка", "notes:create")])
    await reply_callback(callback, _format_notes(items), inline_keyboard(rows))


@router.callback_query(lambda c: c.data == "notes:create")
async def cb_note_create_start(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    await _uc(context, session)
    await state.set_state(NoteCreateFSM.title)
    await reply_callback(callback, "Введите заголовок заметки:", cancel_keyboard())


@router.message(NoteCreateFSM.title)
async def msg_note_title(message: Message, state: FSMContext) -> None:
    text = _norm(message.text)
    if not text:
        await message.answer("Введите заголовок.")
        return
    await state.update_data(title=text)
    await state.set_state(NoteCreateFSM.content)
    await message.answer("Содержимое:", reply_markup=optional_keyboard())


@router.message(NoteCreateFSM.content)
async def msg_note_content(message: Message, context: Context, session: Any, state: FSMContext) -> None:
    data = await state.get_data()
    couple, user_id = await _uc(context, session)
    content = None if _is_skip(message.text) else _norm(message.text)
    note = await NoteService(session).create_note(couple.id, user_id, _norm(data.get("title")), content=content)
    await state.clear()
    await message.answer(f"Заметка «{note.title}» создана.", reply_markup=_note_markup(note))


@router.callback_query(lambda c: c.data and c.data.startswith("note:") and c.data.split(":")[1].isdigit())
async def cb_note_detail(callback: CallbackQuery, context: Context, session: Any) -> None:
    note, _, _ = await _note_by_callback(callback, context, session)
    await reply_callback(
        callback,
        f"📝 {note.title}\n{note.content or ''}",
        _note_markup(note),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("note:edit:"))
async def cb_note_edit(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    note, _, _ = await _note_by_callback(callback, context, session)
    await state.set_data({"flow": "note_edit", "item_id": note.id, "field": "title", "edit": True})
    await state.set_state(NoteEditFSM.value)
    await reply_callback(callback, "Введите новое название:", _note_edit_keyboard(note.id))


def _note_edit_keyboard(note_id: int) -> Any:
    return inline_keyboard(
        [
            [("Заголовок", f"note:field:{note_id}:title"),
             ("Содержимое", f"note:field:{note_id}:content")],
            [("↩️ Назад", f"note:{note_id}")],
        ]
    )


@router.callback_query(lambda c: c.data and c.data.startswith("note:field:"))
async def cb_note_field(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    await state.update_data(item_id=callback_int(parts[2]), field=parts[3])
    await state.set_state(NoteEditFSM.value)
    prompt = "Введите новое название:" if parts[3] == "title" else "Введите новое содержимое:"
    keyboard = optional_keyboard() if parts[3] == "content" else cancel_keyboard()
    await reply_callback(callback, prompt, keyboard)


@router.message(NoteEditFSM.value)
async def msg_note_edit_value(message: Message, context: Context, session: Any, state: FSMContext) -> None:
    data = await state.get_data()
    field = data.get("field")
    note_id = callback_int(data.get("item_id"))
    text = _norm(message.text)
    couple, user_id = await _uc(context, session)
    service = NoteService(session)
    if field == "title":
        if not text:
            await message.answer("Введите заголовок.")
            return
        note = await service.update_note(couple.id, user_id, note_id, title=text)
    elif field == "content":
        content = None if _is_skip(text) else text
        note = await service.update_note(couple.id, user_id, note_id, content=content)
    else:
        await message.answer("Неизвестное поле.")
        return
    await state.clear()
    await message.answer(f"📝 {note.title}\n{note.content or ''}", reply_markup=_note_markup(note))


@router.callback_query(lambda c: c.data and c.data.startswith("note:delete:"))
async def cb_note_delete(callback: CallbackQuery, context: Context, session: Any) -> None:
    note_id = callback_int(callback.data.split(":")[2])
    couple, user_id = await _uc(context, session)
    await NoteService(session).delete_note(couple.id, user_id, note_id)
    await reply_callback(callback, "Заметка удалена.", back_to_menu_keyboard())


CHALLENGE_SCOPE_LABELS = {"PERSONAL": "Только я", "COUPLE": "Мы вместе"}
CHALLENGE_TYPE_LABELS = {"SIMPLE": "Выполнение", "SAVINGS": "Экономия денег"}
MONTH_NAMES = (
    "",
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
)


def _money(value: Decimal | None) -> str:
    amount = (value or Decimal("0.00")).quantize(Decimal("0.01"))
    text = f"{amount:,.2f}".replace(",", " ").replace(".00", "")
    return f"{text} ₽"


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def _calendar_keyboard(kind: str, month: date, min_date: date | None = None) -> Any:
    first_day = date(month.year, month.month, 1)
    previous_month = _add_months(first_day, -1)
    next_month = _add_months(first_day, 1)
    rows: list[list[tuple[str, str]]] = [
        [
            ("‹", f"chl:new:cal:{kind}:{previous_month.isoformat()}"),
            (f"{MONTH_NAMES[first_day.month]} {first_day.year}", "chl:new:cal:noop"),
            ("›", f"chl:new:cal:{kind}:{next_month.isoformat()}"),
        ],
        [("Пн", "chl:new:cal:noop"), ("Вт", "chl:new:cal:noop"), ("Ср", "chl:new:cal:noop"),
         ("Чт", "chl:new:cal:noop"), ("Пт", "chl:new:cal:noop"), ("Сб", "chl:new:cal:noop"),
         ("Вс", "chl:new:cal:noop")],
    ]
    days_in_month = monthrange(first_day.year, first_day.month)[1]
    row: list[tuple[str, str]] = []
    for _ in range(first_day.weekday()):
        row.append((" ", "chl:new:cal:noop"))
    for day in range(1, days_in_month + 1):
        current = date(first_day.year, first_day.month, day)
        if min_date is not None and current < min_date:
            row.append(("·", "chl:new:cal:noop"))
        else:
            row.append((str(day), f"chl:new:date:{kind}:{current.isoformat()}"))
        if len(row) == 7:
            rows.append(row)
            row = []
    if row:
        while len(row) < 7:
            row.append((" ", "chl:new:cal:noop"))
        rows.append(row)
    rows.append([("Отмена", "chl:new:cancel")])
    return inline_keyboard(rows)


def _challenge_confirm_keyboard() -> Any:
    return inline_keyboard([[("✅ Создать челлендж", "chl:new:confirm")], [("Отмена", "chl:new:cancel")]])


def _challenge_progress(challenge: Any, participant_id: int, today: date) -> str:
    entries = {
        entry.entry_date: entry.status
        for entry in challenge.entries
        if entry.user_id == participant_id
    }
    total_days = (challenge.end_date - challenge.start_date).days + 1
    symbols: list[str] = []
    max_days = min(total_days, 62)
    for offset in range(max_days):
        day = challenge.start_date + timedelta(days=offset)
        status = entries.get(day)
        if status == "SUCCESS":
            symbols.append("🟩")
        elif status == "MISSED":
            symbols.append("⬜")
        else:
            symbols.append("·")
    if total_days > max_days:
        symbols.append("…")
    return "".join(symbols)


def _user_name(user: Any | None, fallback: str) -> str:
    if user is None:
        return fallback
    return user.display_name or user.first_name or user.username or fallback


def _participant_daily_amount(challenge: Any, user_id: int) -> Decimal | None:
    for participant in challenge.participants:
        if participant.user_id == user_id:
            return participant.daily_amount
    return None


def _challenge_entry(challenge: Any, user_id: int, entry_date: date) -> Any | None:
    for entry in challenge.entries:
        if entry.user_id == user_id and entry.entry_date == entry_date:
            return entry
    return None


def _challenge_status_label(entry: Any | None) -> str:
    if entry is None:
        return "нет отметки"
    if entry.status == "SUCCESS":
        return "выполнено"
    return "пропуск"


def _challenge_icon(challenge: Any) -> str:
    return "💰" if challenge.challenge_type == "SAVINGS" else "🎯"


def _challenge_success_label(challenge: Any, day: str) -> str:
    if challenge.challenge_type == "SAVINGS":
        return f"✅ Не покупал {day}"
    return f"✅ Выполнено {day}"


def _challenge_missed_label(challenge: Any, day: str) -> str:
    if challenge.challenge_type == "SAVINGS":
        return f"☕ Купил {day}"
    return f"✖️ Пропуск {day}"


def _challenge_text(challenge: Any, viewer_id: int, today: date) -> str:
    participant_by_id = {participant.user_id: participant for participant in challenge.participants}
    today_entry = _challenge_entry(challenge, viewer_id, today)
    lines = [
        f"{_challenge_icon(challenge)} {challenge.title}",
        f"{challenge.start_date.strftime('%d.%m')}–{challenge.end_date.strftime('%d.%m')}",
        f"Сегодня: {_challenge_status_label(today_entry)}",
        "",
    ]
    visible_participants = challenge.participants
    if challenge.scope == "PERSONAL":
        visible_participants = [participant_by_id[viewer_id]]
    for participant in visible_participants:
        name = _user_name(participant.user, str(participant.user_id))
        lines.append(f"{name}:")
        if challenge.challenge_type == "SAVINGS":
            amount = _participant_daily_amount(challenge, participant.user_id)
            plan = f"{_money(amount)} в день" if amount is not None else "не настроен"
            lines.append(f"План: {plan}")
        lines.append(_challenge_progress(challenge, participant.user_id, today))
        lines.append("")
    if challenge.challenge_type == "SAVINGS":
        stats = ChallengeService.calculate_stats(challenge, today)
        lines.append(f"Потрачено: {_money(stats.actual_spending)}")
        if stats.calculated_savings >= 0:
            lines.append(f"Расчётная экономия: {_money(stats.calculated_savings)}")
        else:
            lines.append(f"Перерасход: {_money(abs(stats.calculated_savings))}")
    return "\n".join(lines).strip()


def _challenge_detail_markup(
    challenge: Any,
    user_id: int,
    today: date,
    show_today_prompt: bool = True,
) -> Any:
    rows: list[list[tuple[str, str]]] = []
    if challenge.challenge_type == "SAVINGS" and _participant_daily_amount(challenge, user_id) is None:
        rows.append([("💰 Настроить план", f"chl:amount:{challenge.id}")])
    if (
        show_today_prompt
        and challenge.start_date <= today <= challenge.end_date
        and _challenge_entry(challenge, user_id, today) is None
    ):
        rows.extend(
            [
                [(_challenge_success_label(challenge, "сегодня"), f"chl:ok:{challenge.id}")],
                [(_challenge_missed_label(challenge, "сегодня"), f"chl:miss:{challenge.id}")],
            ]
        )
    yesterday = today - timedelta(days=1)
    if (
        challenge.start_date <= yesterday <= challenge.end_date
        and _challenge_entry(challenge, user_id, yesterday) is None
    ):
        rows.append(
            [
                (_challenge_success_label(challenge, "вчера"), f"chl:yok:{challenge.id}"),
                (_challenge_missed_label(challenge, "вчера"), f"chl:ymiss:{challenge.id}"),
            ]
        )
    rows.append([("🔄 Обновить", f"chl:status:{challenge.id}")])
    rows.append([("↩️ К челленджам", "challenges:list")])
    return inline_keyboard(rows)


def _challenge_summary(data: dict[str, Any]) -> str:
    lines = [
        "🎯 Новый челлендж",
        f"Название: {data.get('title')}",
        f"Участники: {CHALLENGE_SCOPE_LABELS.get(data.get('scope'), '-')}",
        f"Что отслеживаем: {CHALLENGE_TYPE_LABELS.get(data.get('challenge_type'), '-')}",
        f"Начало: {data.get('start_date')}",
        f"Окончание: {data.get('end_date')}",
    ]
    if data.get("challenge_type") == "SAVINGS":
        participant_plans = data.get("participant_plans") or []
        participant_amounts = data.get("participant_amounts") or {}
        if participant_plans:
            lines.append("План на день:")
            for participant in participant_plans:
                user_id = participant["user_id"]
                amount = participant_amounts.get(user_id) or participant_amounts.get(str(user_id))
                if amount is None:
                    lines.append(f"- {participant['name']}: настроит отдельно")
                else:
                    lines.append(f"- {participant['name']}: {_money(Decimal(str(amount)))}")
    return "\n".join(lines)


async def _challenge_participant_plans(context: Context, session: Any, scope: str) -> list[dict[str, Any]]:
    couple, user_id = await _uc(context, session)
    members = await CoupleMemberRepository(session).get_members(couple.id)
    if scope == "PERSONAL":
        members = [member for member in members if member.user_id == user_id]
    else:
        members = sorted(members, key=lambda member: member.user_id != user_id)
    plans = []
    for member in members:
        plans.append(
            {
                "user_id": member.user_id,
                "name": _user_name(member.user, str(member.user_id)),
            }
        )
    return plans


async def _ask_next_challenge_amount(event: CallbackQuery | Message, state: FSMContext) -> None:
    data = await state.get_data()
    participant_plans = data.get("participant_plans") or []
    index = int(data.get("participant_amount_index", 0))
    required_amount_count = 1 if data.get("challenge_type") == "SAVINGS" else len(participant_plans)
    if index >= min(len(participant_plans), required_amount_count):
        await state.set_state(ChallengeCreateFSM.confirm)
        text = _challenge_summary(data)
        if isinstance(event, CallbackQuery):
            await reply_callback(event, text, _challenge_confirm_keyboard())
        else:
            await event.answer("Проверьте данные перед созданием:", reply_markup=ReplyKeyboardRemove())
            await event.answer(text, reply_markup=_challenge_confirm_keyboard())
        return
    text = "Ваш план трат в день? Например: 300"
    if isinstance(event, CallbackQuery):
        await reply_callback(event, text, cancel_keyboard())
    else:
        await event.answer(text, reply_markup=cancel_keyboard())


@router.callback_query(lambda c: c.data and c.data.startswith("challenges:list"))
async def cb_challenges_list(callback: CallbackQuery, context: Context, session: Any) -> None:
    couple, user_id = await _uc(context, session)
    all_items = await ChallengeService(session).list_challenges(couple.id, user_id)
    items, page, page_count = paginate(
        all_items, _callback_page(callback, "challenges:list")
    )
    await reply_callback(
        callback,
        _format_challenges(items, user_id),
        _challenge_list_keyboard(items, page, page_count),
    )


@router.callback_query(lambda c: c.data == "challenges:create")
async def cb_challenge_create_start(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    _, user_id = await _uc(context, session)
    await state.set_data({"flow": "challenge_create", "created_by": user_id})
    await state.set_state(ChallengeCreateFSM.title)
    await reply_callback(callback, "Название челленджа:", cancel_keyboard())


@router.message(ChallengeCreateFSM.title)
async def msg_challenge_title(message: Message, state: FSMContext) -> None:
    text = _norm(message.text)
    if not text:
        await message.answer("Введите название челленджа.")
        return
    await state.update_data(title=text)
    await state.set_state(ChallengeCreateFSM.scope)
    await message.answer(
        "Кто участвует в челлендже?",
        reply_markup=inline_keyboard(
            [[("👤 Только я", "chl:new:scope:PERSONAL"), ("👥 Мы вместе", "chl:new:scope:COUPLE")]]
        ),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("chl:new:scope:"))
async def cb_challenge_scope(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    scope = callback.data.split(":")[-1]
    participant_plans = await _challenge_participant_plans(context, session, scope)
    await state.update_data(scope=scope, participant_plans=participant_plans)
    await state.set_state(ChallengeCreateFSM.challenge_type)
    await reply_callback(
        callback,
        "Что отслеживаем?",
        inline_keyboard(
            [[("✅ Выполнение", "chl:new:type:SIMPLE"), ("💰 Экономию денег", "chl:new:type:SAVINGS")]]
        ),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("chl:new:type:"))
async def cb_challenge_type(callback: CallbackQuery, context: Context, state: FSMContext) -> None:
    challenge_type = callback.data.split(":")[-1]
    await state.update_data(challenge_type=challenge_type)
    await state.set_state(ChallengeCreateFSM.start_date)
    await reply_callback(
        callback,
        "Дата начала:",
        _calendar_keyboard("start", context.local_date()),
    )


@router.callback_query(lambda c: c.data == "chl:new:start:today")
async def cb_challenge_start_today(
    callback: CallbackQuery, context: Context, state: FSMContext
) -> None:
    await state.update_data(start_date=context.local_date().isoformat())
    await state.set_state(ChallengeCreateFSM.end_date)
    await reply_callback(
        callback,
        "Дата окончания:",
        _calendar_keyboard("end", context.local_date(), context.local_date()),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("chl:new:cal:"))
async def cb_challenge_calendar_nav(callback: CallbackQuery, state: FSMContext) -> None:
    data = callback.data or ""
    if data == "chl:new:cal:noop":
        await alert_callback(callback, "Выберите дату.")
        return
    state_data = await state.get_data()
    if state_data.get("flow") != "challenge_create":
        await alert_callback(callback, "Форма уже закрыта.")
        return
    _, _, _, kind, month_raw = data.split(":", 4)
    month = date.fromisoformat(month_raw)
    min_date = None
    if kind == "end" and state_data.get("start_date"):
        min_date = date.fromisoformat(state_data["start_date"])
    title = "Дата начала:" if kind == "start" else "Дата окончания:"
    await reply_callback(callback, title, _calendar_keyboard(kind, month, min_date))


@router.callback_query(lambda c: c.data and c.data.startswith("chl:new:date:"))
async def cb_challenge_date_select(callback: CallbackQuery, state: FSMContext) -> None:
    state_data = await state.get_data()
    if state_data.get("flow") != "challenge_create":
        await alert_callback(callback, "Форма уже закрыта.")
        return
    _, _, _, kind, value = (callback.data or "").split(":", 4)
    selected = date.fromisoformat(value)
    if kind == "start":
        await state.update_data(start_date=selected.isoformat())
        await state.set_state(ChallengeCreateFSM.end_date)
        await reply_callback(
            callback,
            "Дата окончания:",
            _calendar_keyboard("end", selected, selected),
        )
        return
    data = await state.get_data()
    start = date.fromisoformat(data["start_date"])
    if selected < start:
        await alert_callback(callback, "Дата окончания не может быть раньше даты начала.")
        return
    await _finish_challenge_dates(callback, state, selected)


@router.message(ChallengeCreateFSM.start_date)
async def msg_challenge_start_date(message: Message, state: FSMContext) -> None:
    start = _parse_date(message.text)
    if start is None:
        await message.answer("Введите дату в формате дд.мм.гггг.")
        return
    await state.update_data(start_date=start.isoformat())
    await state.set_state(ChallengeCreateFSM.end_date)
    await message.answer(
        "Дата окончания:",
        reply_markup=_calendar_keyboard("end", start, start),
    )


@router.message(ChallengeCreateFSM.end_date)
async def msg_challenge_end_date(message: Message, state: FSMContext) -> None:
    end = _parse_date(message.text)
    if end is None:
        await message.answer("Введите дату в формате дд.мм.гггг.")
        return
    data = await state.get_data()
    start = date.fromisoformat(data["start_date"])
    if end < start:
        await message.answer("Дата окончания не может быть раньше даты начала.")
        return
    await _finish_challenge_dates(message, state, end)


async def _finish_challenge_dates(event: CallbackQuery | Message, state: FSMContext, end: date) -> None:
    await state.update_data(end_date=end.isoformat())
    data = await state.get_data()
    if data.get("challenge_type") == "SAVINGS":
        await state.set_state(ChallengeCreateFSM.daily_amount)
        await state.update_data(participant_amounts={}, participant_amount_index=0)
        await _ask_next_challenge_amount(event, state)
        return
    data = await state.get_data()
    await state.set_state(ChallengeCreateFSM.confirm)
    if isinstance(event, CallbackQuery):
        await reply_callback(event, _challenge_summary(data), _challenge_confirm_keyboard())
    else:
        await event.answer(_challenge_summary(data), reply_markup=_challenge_confirm_keyboard())


@router.message(ChallengeCreateFSM.daily_amount)
async def msg_challenge_daily_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = ChallengeService.normalize_money(message.text)
    except ValidationError as exc:
        await message.answer(exc.message)
        return
    if amount is None:
        await message.answer("Введите сумму на день.")
        return
    data = await state.get_data()
    participant_plans = data.get("participant_plans") or []
    index = int(data.get("participant_amount_index", 0))
    participant_amounts = data.get("participant_amounts") or {}
    if index >= len(participant_plans):
        await message.answer("Все суммы уже указаны.")
        await _ask_next_challenge_amount(message, state)
        return
    participant = participant_plans[index]
    participant_amounts[participant["user_id"]] = str(amount)
    await state.update_data(
        participant_amounts=participant_amounts,
        participant_amount_index=index + 1,
    )
    await _ask_next_challenge_amount(message, state)


@router.callback_query(lambda c: c.data == "chl:new:cancel")
async def cb_challenge_create_cancel(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get("flow") != "challenge_create":
        await alert_callback(callback, "Форма уже закрыта. Челлендж не изменён.")
        return
    await state.clear()
    couple, user_id = await _uc(context, session)
    items = await ChallengeService(session).list_challenges(couple.id, user_id)
    await reply_callback(
        callback,
        "Создание отменено.\n\n" + _format_challenges(items, user_id),
        _challenge_list_keyboard(items),
    )


@router.callback_query(lambda c: c.data == "chl:new:confirm")
async def cb_challenge_create_confirm(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    data = await state.get_data()
    required = {"title", "scope", "challenge_type", "start_date", "end_date"}
    if not required.issubset(data):
        await state.clear()
        await alert_callback(callback, "Форма устарела. Создайте челлендж заново.")
        return
    couple, user_id = await _uc(context, session)
    try:
        challenge = await ChallengeService(session).create_challenge(
            couple_id=couple.id,
            created_by=user_id,
            title=_norm(data.get("title")),
            scope=data.get("scope"),
            challenge_type=data.get("challenge_type"),
            start_date=date.fromisoformat(data["start_date"]),
            end_date=date.fromisoformat(data["end_date"]),
            participant_daily_amounts={
                int(user_id): Decimal(str(amount))
                for user_id, amount in (data.get("participant_amounts") or {}).items()
            },
        )
    except ValidationError as exc:
        await alert_callback(callback, exc.message)
        return
    await state.clear()
    challenge = await ChallengeService(session).get_challenge(couple.id, user_id, challenge.id)
    notification_failed = await _notify_challenge_partners(callback, challenge, user_id)
    today = context.local_date()
    text = f"Челлендж создан.\n\n{_challenge_text(challenge, user_id, today)}"
    if notification_failed:
        text += "\n\nНе удалось отправить уведомление партнёру."
    await reply_callback(
        callback,
        text,
        _challenge_detail_markup(challenge, user_id, today, show_today_prompt=False),
    )


async def _notify_challenge_partners(callback: CallbackQuery, challenge: Any, creator_id: int) -> bool:
    if challenge.scope != "COUPLE":
        return False
    failed = False
    for participant in challenge.participants:
        if participant.user_id == creator_id or participant.user is None:
            continue
        try:
            await callback.bot.send_message(
                participant.user.telegram_id,
                (
                    f"Появился общий челлендж: {challenge.title}"
                    "\nОткрой его и настрой свой план на день."
                ),
                reply_markup=inline_keyboard(
                    [
                        [("💰 Настроить план", f"chl:amount:{challenge.id}")],
                        [("🎯 Открыть челлендж", f"chl:status:{challenge.id}")],
                    ]
                ),
            )
        except TelegramAPIError:
            failed = True
            logger.exception(
                "Failed to notify participant id=%s about challenge id=%s",
                participant.user_id,
                challenge.id,
            )
    return failed


@router.callback_query(lambda c: c.data and c.data.startswith("chl:amount:"))
async def cb_challenge_amount_start(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    challenge_id = callback_int(callback.data.split(":")[2])
    couple, user_id = await _uc(context, session)
    challenge = await ChallengeService(session).get_challenge(couple.id, user_id, challenge_id)
    if challenge.challenge_type != "SAVINGS":
        await alert_callback(callback, "План на день есть только для экономии.")
        return
    await state.set_data({"flow": "challenge_amount", "challenge_id": challenge.id})
    await state.set_state(ChallengeAmountFSM.daily_amount)
    await reply_callback(callback, "Ваш план трат в день? Например: 300", cancel_keyboard())


@router.message(ChallengeAmountFSM.daily_amount)
async def msg_challenge_amount_save(message: Message, context: Context, session: Any, state: FSMContext) -> None:
    data = await state.get_data()
    if "challenge_id" not in data:
        await state.clear()
        await message.answer("Форма устарела. Откройте челлендж заново.")
        return
    challenge_id = callback_int(data.get("challenge_id"))
    couple, user_id = await _uc(context, session)
    service = ChallengeService(session)
    try:
        await service.set_daily_amount(couple.id, user_id, challenge_id, message.text)
    except ValidationError as exc:
        await message.answer(exc.message)
        return
    await state.clear()
    challenge = await service.get_challenge(couple.id, user_id, challenge_id)
    today = context.local_date()
    await message.answer(
        "План сохранён.\n\n" + _challenge_text(challenge, user_id, today),
        reply_markup=_challenge_detail_markup(challenge, user_id, today),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("chl:") and c.data.split(":")[1].isdigit())
async def cb_challenge_detail(callback: CallbackQuery, context: Context, session: Any) -> None:
    challenge_id = callback_int(callback.data.split(":")[1])
    couple, user_id = await _uc(context, session)
    challenge = await ChallengeService(session).get_challenge(couple.id, user_id, challenge_id)
    today = context.local_date()
    await reply_callback(
        callback,
        _challenge_text(challenge, user_id, today),
        _challenge_detail_markup(challenge, user_id, today),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("chl:status:"))
async def cb_challenge_status(callback: CallbackQuery, context: Context, session: Any) -> None:
    challenge_id = callback_int(callback.data.split(":")[2])
    couple, user_id = await _uc(context, session)
    challenge = await ChallengeService(session).get_challenge(couple.id, user_id, challenge_id)
    today = context.local_date()
    await reply_callback(
        callback,
        _challenge_text(challenge, user_id, today),
        _challenge_detail_markup(challenge, user_id, today),
    )


async def _record_challenge_status(
    callback: CallbackQuery,
    context: Context,
    session: Any,
    state: FSMContext,
    status: str,
    entry_date: date,
) -> None:
    challenge_id = callback_int(callback.data.split(":")[2])
    couple, user_id = await _uc(context, session)
    service = ChallengeService(session)
    challenge = await service.get_challenge(couple.id, user_id, challenge_id)
    if status == "MISSED" and challenge.challenge_type == "SAVINGS":
        await state.set_data(
            {
                "flow": "challenge_entry",
                "challenge_id": challenge.id,
                "entry_date": entry_date.isoformat(),
            }
        )
        await state.set_state(ChallengeEntryFSM.spent_amount)
        quick_amount = _participant_daily_amount(challenge, user_id)
        rows = []
        if quick_amount is not None:
            quick = str(quick_amount)
            rows.append([(_money(quick_amount), f"chl:spend:{quick}")])
        await reply_callback(
            callback,
            "Сколько потратили?",
            inline_keyboard(rows) if rows else cancel_keyboard(),
        )
        return
    try:
        await service.record_entry(
            couple.id,
            user_id,
            challenge.id,
            entry_date,
            status,
            today=context.local_date(),
        )
    except ValidationError as exc:
        await alert_callback(callback, exc.message)
        return
    challenge = await service.get_challenge(couple.id, user_id, challenge.id)
    today = context.local_date()
    await reply_callback(
        callback,
        _challenge_text(challenge, user_id, today),
        _challenge_detail_markup(challenge, user_id, today),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("chl:ok:"))
async def cb_challenge_success(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    await _record_challenge_status(
        callback, context, session, state, "SUCCESS", context.local_date()
    )


@router.callback_query(lambda c: c.data and c.data.startswith("chl:miss:"))
async def cb_challenge_missed(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    await _record_challenge_status(
        callback, context, session, state, "MISSED", context.local_date()
    )


@router.callback_query(lambda c: c.data and c.data.startswith("chl:yok:"))
async def cb_challenge_yesterday_success(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    await _record_challenge_status(
        callback,
        context,
        session,
        state,
        "SUCCESS",
        context.local_date() - timedelta(days=1),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("chl:ymiss:"))
async def cb_challenge_yesterday_missed(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    await _record_challenge_status(
        callback,
        context,
        session,
        state,
        "MISSED",
        context.local_date() - timedelta(days=1),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("chl:spend:"))
async def cb_challenge_spend_quick(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    amount = callback.data.split(":", 2)[2]
    await _save_challenge_spend(callback, context, session, state, amount)


@router.message(ChallengeEntryFSM.spent_amount)
async def msg_challenge_spend(message: Message, context: Context, session: Any, state: FSMContext) -> None:
    await _save_challenge_spend(message, context, session, state, message.text)


async def _save_challenge_spend(event: CallbackQuery | Message, context: Context, session: Any, state: FSMContext, amount_text: str | None) -> None:
    data = await state.get_data()
    if not {"challenge_id", "entry_date"}.issubset(data):
        await state.clear()
        if isinstance(event, CallbackQuery):
            await alert_callback(event, "Форма устарела. Откройте челлендж заново.")
        else:
            await event.answer("Форма устарела. Откройте челлендж заново.")
        return
    challenge_id = callback_int(data.get("challenge_id"))
    entry_date = date.fromisoformat(data["entry_date"])
    couple, user_id = await _uc(context, session)
    service = ChallengeService(session)
    try:
        amount = ChallengeService.normalize_money(amount_text)
        await service.record_entry(
            couple.id,
            user_id,
            challenge_id,
            entry_date,
            "MISSED",
            amount,
            today=context.local_date(),
        )
    except ValidationError as exc:
        if isinstance(event, CallbackQuery):
            await alert_callback(event, exc.message)
        else:
            await event.answer(exc.message)
        return
    await state.clear()
    challenge = await service.get_challenge(couple.id, user_id, challenge_id)
    if isinstance(event, CallbackQuery):
        today = context.local_date()
        await reply_callback(
            event,
            _challenge_text(challenge, user_id, today),
            _challenge_detail_markup(challenge, user_id, today),
        )
    else:
        today = context.local_date()
        await event.answer(
            _challenge_text(challenge, user_id, today),
            reply_markup=_challenge_detail_markup(challenge, user_id, today),
        )


@router.callback_query(lambda c: c.data == "settings:display")
async def cb_settings_display(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    await _uc(context, session)
    await state.set_state(SettingsDisplayFSM.display_name)
    await reply_callback(callback, "Введите новое имя:", cancel_keyboard())


@router.message(SettingsDisplayFSM.display_name)
async def msg_settings_display(message: Message, context: Context, session: Any, state: FSMContext) -> None:
    name = _norm(message.text)
    if not name:
        await message.answer("Введите имя.")
        return
    user_id = require_user_id(context)
    try:
        await SettingsService(session).update_user_display_name(user_id, name)
    except ValidationError as exc:
        await message.answer(exc.message)
        return
    await state.clear()
    await message.answer("Имя сохранено.", reply_markup=MAIN_MENU)


@router.callback_query(lambda c: c.data == "settings:timezone")
async def cb_settings_timezone(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    await _uc(context, session)
    await state.set_state(SettingsTimezoneFSM.timezone)
    await reply_callback(callback, "Введите IANA-часовой пояс (например, Europe/Moscow):", cancel_keyboard())


@router.message(SettingsTimezoneFSM.timezone)
async def msg_settings_timezone(message: Message, context: Context, session: Any, state: FSMContext) -> None:
    tz = _norm(message.text)
    if not tz:
        await message.answer("Введите часовой пояс.")
        return
    user_id = require_user_id(context)
    try:
        await SettingsService(session).set_user_timezone(user_id, tz)
    except ValidationError as exc:
        await message.answer(exc.message)
        return
    await state.clear()
    await message.answer("Часовой пояс сохранён.", reply_markup=MAIN_MENU)


@router.callback_query(lambda c: c.data == "settings:couple")
async def cb_settings_couple(callback: CallbackQuery, context: Context, session: Any, state: FSMContext) -> None:
    await _uc(context, session)
    await state.set_state(CoupleNameFSM.name)
    await reply_callback(callback, "Введите имя пары:", cancel_keyboard())


@router.message(CoupleNameFSM.name)
async def msg_settings_couple(message: Message, context: Context, session: Any, state: FSMContext) -> None:
    name = _norm(message.text)
    if not name:
        await message.answer("Введите имя.")
        return
    couple, user_id = await _uc(context, session)
    try:
        await CoupleService(session).update_couple_name(couple.id, user_id, name)
    except ValidationError as exc:
        await message.answer(exc.message)
        return
    await state.clear()
    await message.answer("Имя пары сохранено.", reply_markup=MAIN_MENU)
