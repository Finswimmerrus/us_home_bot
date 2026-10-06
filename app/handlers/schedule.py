from __future__ import annotations

import asyncio
from typing import Any

from aiogram import Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ValidationError
from app.handlers.fsm import ScheduleFSM
from app.handlers.start import MAIN_MENU
from app.models.schedule import ScheduleEntry
from app.services.schedule_service import (
    DAY_NAMES,
    ScheduleDraft,
    ScheduleService,
    entry_to_draft,
    format_time_range,
    format_weekdays,
    parse_time_range,
    parse_weekdays,
)
from app.utils.callbacks import (
    CANCEL_BUTTON,
    answer_callback,
    callback_int,
    cancel_keyboard,
    get_callback_message,
    inline_keyboard,
    require_user_id,
)
from app.utils.context import Context
from app.utils.markdown_table import MarkdownTable, render_table_png

router = Router()


def _entry_summary(entry: ScheduleEntry) -> str:
    days = format_weekdays(parse_weekdays(entry.weekdays))
    time = format_time_range(entry.start_minute, entry.end_minute)
    return f"{entry.title} · {days} · {time}"


def _schedule_keyboard(entries: list[ScheduleEntry]) -> Any:
    rows = [
        [(f"✏️ {_entry_summary(entry)[:48]}", f"schedule:item:{entry.id}")]
        for entry in entries
    ]
    rows.append([("➕ Добавить занятие", "schedule:add")])
    rows.append([("↩️ Главное меню", "section:back")])
    return inline_keyboard(rows)


def _days_keyboard(selected: set[int]) -> Any:
    day_buttons = [
        (f"{'✅ ' if day in selected else ''}{name}", f"schedule:day:{day}")
        for day, name in enumerate(DAY_NAMES)
    ]
    return inline_keyboard(
        [
            day_buttons[:4],
            day_buttons[4:],
            [("Готово", "schedule:days:done")],
            [("Отмена", "schedule:flow:cancel")],
        ]
    )


def _table_for_entries(entries: list[ScheduleEntry]) -> MarkdownTable:
    ordered = sorted(
        entries,
        key=lambda entry: (
            min(parse_weekdays(entry.weekdays), default=7),
            entry.start_minute,
            entry.title.casefold(),
        ),
    )
    rows = [("Занятие", "Дни недели", "Время")]
    rows.extend(
        (
            entry.title,
            format_weekdays(parse_weekdays(entry.weekdays)),
            format_time_range(entry.start_minute, entry.end_minute),
        )
        for entry in ordered
    )
    return MarkdownTable(
        rows=tuple(rows),
        alignments=("left", "center", "center"),
        title="Моё расписание",
    )


async def _send_schedule(message: Message, service: ScheduleService, user_id: int) -> None:
    entries = await service.list_entries(user_id)
    if not entries:
        await message.answer(
            "📅 Расписание пока пусто.",
            reply_markup=_schedule_keyboard(entries),
        )
        return
    image = await asyncio.to_thread(render_table_png, _table_for_entries(entries))
    await message.answer_photo(
        BufferedInputFile(image, filename="schedule.png"),
        caption="📅 Моё расписание",
        reply_markup=_schedule_keyboard(entries),
    )


def _draft_from_data(data: dict[str, Any]) -> ScheduleDraft:
    return ScheduleService.validate_draft(
        str(data.get("title", "")),
        [int(day) for day in data.get("weekdays", [])],
        int(data.get("start_minute", -1)),
        int(data.get("end_minute", -1)),
    )


async def _show_updated_schedule(
    message: Message,
    state: FSMContext,
    service: ScheduleService,
    user_id: int,
    notice: str = "Расписание обновлено.",
) -> None:
    await state.clear()
    await message.answer(notice, reply_markup=ReplyKeyboardRemove())
    await _send_schedule(message, service, user_id)


async def _submit_candidate(
    message: Message,
    state: FSMContext,
    service: ScheduleService,
    user_id: int,
) -> None:
    data = await state.get_data()
    draft = _draft_from_data(data)
    entry_id = data.get("entry_id")
    parsed_entry_id = int(entry_id) if entry_id is not None else None
    conflicts = await service.find_conflicts(user_id, draft, exclude_id=parsed_entry_id)
    if not conflicts:
        await service.save(user_id, draft, entry_id=parsed_entry_id)
        await _show_updated_schedule(message, state, service, user_id)
        return

    await state.set_state(ScheduleFSM.conflict)
    conflict_lines = "\n".join(f"• {_entry_summary(entry)}" for entry in conflicts)
    candidate = (
        f"{draft.title} · {format_weekdays(draft.weekdays)} · "
        f"{format_time_range(draft.start_minute, draft.end_minute)}"
    )
    await message.answer(
        "⚠️ Обнаружено пересечение.\n\n"
        f"Новое расписание:\n• {candidate}\n\n"
        f"Уже сохранено:\n{conflict_lines}\n\n"
        "Выберите, какие занятия оставить:",
        reply_markup=inline_keyboard(
            [
                [("Оставить новое, удалить старое", "schedule:conflict:replace")],
                [("Оставить сохранённое", "schedule:conflict:keep")],
            ]
        ),
    )


@router.message(
    StateFilter(ScheduleFSM.title, ScheduleFSM.days, ScheduleFSM.time, ScheduleFSM.conflict),
    Command("cancel"),
)
async def cancel_schedule_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.", reply_markup=MAIN_MENU)


@router.message(
    StateFilter(ScheduleFSM.title, ScheduleFSM.days, ScheduleFSM.time, ScheduleFSM.conflict),
    lambda message: (message.text or "").strip().lower() == CANCEL_BUTTON.lower(),
)
async def cancel_schedule_message(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.", reply_markup=MAIN_MENU)


@router.message(StateFilter(None), lambda message: message.text == "📅 Расписание")
async def show_schedule(message: Message, context: Context, session: AsyncSession) -> None:
    await _send_schedule(message, ScheduleService(session), require_user_id(context))


@router.callback_query(lambda callback: callback.data == "schedule:list")
async def callback_schedule_list(
    callback: CallbackQuery,
    context: Context,
    session: AsyncSession,
) -> None:
    await answer_callback(callback)
    message = get_callback_message(callback)
    if message is not None:
        await _send_schedule(message, ScheduleService(session), require_user_id(context))


@router.callback_query(lambda callback: callback.data == "schedule:add")
async def callback_schedule_add(callback: CallbackQuery, state: FSMContext) -> None:
    await answer_callback(callback)
    await state.clear()
    await state.set_data({"flow": "create", "weekdays": []})
    await state.set_state(ScheduleFSM.title)
    message = get_callback_message(callback)
    if message is not None:
        await message.answer("Введите название занятия:", reply_markup=cancel_keyboard())


@router.message(ScheduleFSM.title)
async def schedule_title(
    message: Message,
    state: FSMContext,
    context: Context,
    session: AsyncSession,
) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer("Введите название занятия.")
        return
    if len(title) > 200:
        await message.answer("Название должно быть не длиннее 200 символов.")
        return
    await state.update_data(title=title)
    data = await state.get_data()
    if data.get("flow") == "edit":
        await _submit_candidate(
            message,
            state,
            ScheduleService(session),
            require_user_id(context),
        )
        return
    await state.set_state(ScheduleFSM.days)
    await message.answer(
        "Выберите дни недели и нажмите «Готово»:",
        reply_markup=_days_keyboard(set()),
    )


@router.callback_query(lambda callback: callback.data and callback.data.startswith("schedule:day:"))
async def callback_schedule_day(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if await state.get_state() != ScheduleFSM.days.state:
        await answer_callback(callback, "Сначала начните добавление или изменение занятия.", True)
        return
    day = callback_int((callback.data or "").rsplit(":", 1)[-1])
    if day not in range(7):
        await answer_callback(callback, "Некорректный день недели.", True)
        return
    selected = {int(value) for value in data.get("weekdays", [])}
    selected.symmetric_difference_update({day})
    await state.update_data(weekdays=sorted(selected))
    await answer_callback(callback)
    message = get_callback_message(callback)
    if message is not None:
        await message.edit_reply_markup(reply_markup=_days_keyboard(selected))


@router.callback_query(lambda callback: callback.data == "schedule:days:done")
async def callback_schedule_days_done(
    callback: CallbackQuery,
    state: FSMContext,
    context: Context,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    selected = [int(value) for value in data.get("weekdays", [])]
    if not selected:
        await answer_callback(callback, "Выберите хотя бы один день.", True)
        return
    await answer_callback(callback)
    message = get_callback_message(callback)
    if message is None:
        return
    if data.get("flow") == "edit":
        await _submit_candidate(
            message,
            state,
            ScheduleService(session),
            require_user_id(context),
        )
        return
    await state.set_state(ScheduleFSM.time)
    await message.answer("Введите время, например 18:00–19:30:", reply_markup=cancel_keyboard())


@router.message(ScheduleFSM.time)
async def schedule_time(
    message: Message,
    state: FSMContext,
    context: Context,
    session: AsyncSession,
) -> None:
    try:
        start_minute, end_minute = parse_time_range(message.text or "")
    except ValidationError as exc:
        await message.answer(exc.message)
        return
    await state.update_data(start_minute=start_minute, end_minute=end_minute)
    await _submit_candidate(
        message,
        state,
        ScheduleService(session),
        require_user_id(context),
    )


@router.callback_query(lambda callback: callback.data and callback.data.startswith("schedule:item:"))
async def callback_schedule_item(
    callback: CallbackQuery,
    context: Context,
    session: AsyncSession,
) -> None:
    entry_id = callback_int((callback.data or "").rsplit(":", 1)[-1])
    entry = await ScheduleService(session).get_entry(require_user_id(context), entry_id)
    await answer_callback(callback)
    message = get_callback_message(callback)
    if message is not None:
        await message.answer(
            f"📌 {_entry_summary(entry)}",
            reply_markup=inline_keyboard(
                [
                    [("Название", f"schedule:edit:{entry.id}:title")],
                    [
                        ("Дни", f"schedule:edit:{entry.id}:days"),
                        ("Время", f"schedule:edit:{entry.id}:time"),
                    ],
                    [("🗑 Удалить", f"schedule:delete:{entry.id}")],
                    [("↩️ К расписанию", "schedule:list")],
                ]
            ),
        )


@router.callback_query(lambda callback: callback.data and callback.data.startswith("schedule:edit:"))
async def callback_schedule_edit(
    callback: CallbackQuery,
    state: FSMContext,
    context: Context,
    session: AsyncSession,
) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await answer_callback(callback, "Некорректная команда.", True)
        return
    entry_id = callback_int(parts[2])
    field = parts[3]
    service = ScheduleService(session)
    entry = await service.get_entry(require_user_id(context), entry_id)
    draft = entry_to_draft(entry)
    await state.clear()
    await state.set_data(
        {
            "flow": "edit",
            "entry_id": entry.id,
            "title": draft.title,
            "weekdays": list(draft.weekdays),
            "start_minute": draft.start_minute,
            "end_minute": draft.end_minute,
        }
    )
    await answer_callback(callback)
    message = get_callback_message(callback)
    if message is None:
        return
    if field == "title":
        await state.set_state(ScheduleFSM.title)
        await message.answer("Введите новое название:", reply_markup=cancel_keyboard())
    elif field == "days":
        await state.set_state(ScheduleFSM.days)
        await message.answer(
            "Выберите новые дни и нажмите «Готово»:",
            reply_markup=_days_keyboard(set(draft.weekdays)),
        )
    elif field == "time":
        await state.set_state(ScheduleFSM.time)
        await message.answer("Введите новое время, например 18:00–19:30:", reply_markup=cancel_keyboard())
    else:
        await state.clear()
        await message.answer("Неизвестное поле.")


@router.callback_query(lambda callback: callback.data and callback.data.startswith("schedule:delete:"))
async def callback_schedule_delete_confirm(callback: CallbackQuery) -> None:
    entry_id = callback_int((callback.data or "").rsplit(":", 1)[-1])
    await answer_callback(callback)
    message = get_callback_message(callback)
    if message is not None:
        await message.answer(
            "Удалить это занятие?",
            reply_markup=inline_keyboard(
                [
                    [("Удалить", f"schedule:delete-confirmed:{entry_id}")],
                    [("Отмена", f"schedule:item:{entry_id}")],
                ]
            ),
        )


@router.callback_query(
    lambda callback: callback.data and callback.data.startswith("schedule:delete-confirmed:")
)
async def callback_schedule_delete(
    callback: CallbackQuery,
    state: FSMContext,
    context: Context,
    session: AsyncSession,
) -> None:
    entry_id = callback_int((callback.data or "").rsplit(":", 1)[-1])
    service = ScheduleService(session)
    user_id = require_user_id(context)
    await service.delete(user_id, entry_id)
    await answer_callback(callback)
    message = get_callback_message(callback)
    if message is not None:
        await _show_updated_schedule(message, state, service, user_id, "Занятие удалено.")


@router.callback_query(lambda callback: callback.data == "schedule:conflict:replace")
async def callback_schedule_replace_conflicts(
    callback: CallbackQuery,
    state: FSMContext,
    context: Context,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    draft = _draft_from_data(data)
    entry_id = data.get("entry_id")
    parsed_entry_id = int(entry_id) if entry_id is not None else None
    service = ScheduleService(session)
    user_id = require_user_id(context)
    await service.replace_conflicts(user_id, draft, entry_id=parsed_entry_id)
    await answer_callback(callback)
    message = get_callback_message(callback)
    if message is not None:
        await _show_updated_schedule(
            message,
            state,
            service,
            user_id,
            "Новое занятие сохранено, пересекающиеся удалены.",
        )


@router.callback_query(lambda callback: callback.data == "schedule:conflict:keep")
async def callback_schedule_keep_existing(
    callback: CallbackQuery,
    state: FSMContext,
    context: Context,
    session: AsyncSession,
) -> None:
    service = ScheduleService(session)
    user_id = require_user_id(context)
    await answer_callback(callback)
    message = get_callback_message(callback)
    if message is not None:
        await _show_updated_schedule(
            message,
            state,
            service,
            user_id,
            "Сохранённое расписание оставлено без изменений.",
        )


@router.callback_query(lambda callback: callback.data == "schedule:flow:cancel")
async def callback_schedule_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await answer_callback(callback)
    message = get_callback_message(callback)
    if message is not None:
        await message.answer("Отменено.", reply_markup=MAIN_MENU)
