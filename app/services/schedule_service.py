from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFound, ValidationError
from app.models.schedule import ScheduleEntry
from app.repositories.schedules import ScheduleRepository

DAY_NAMES = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
_TIME_RANGE_RE = re.compile(
    r"^\s*(\d{1,2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2})\s*$"
)


@dataclass(frozen=True, slots=True)
class ScheduleDraft:
    title: str
    weekdays: tuple[int, ...]
    start_minute: int
    end_minute: int


def parse_weekdays(value: str) -> tuple[int, ...]:
    if not value:
        return ()
    try:
        days = tuple(sorted({int(day) for day in value.split(",")}))
    except ValueError:
        return ()
    return days if all(0 <= day <= 6 for day in days) else ()


def serialize_weekdays(days: tuple[int, ...] | list[int]) -> str:
    normalized = tuple(sorted(set(days)))
    if not normalized or any(day < 0 or day > 6 for day in normalized):
        raise ValidationError("Выберите хотя бы один день недели.", field="weekdays")
    return ",".join(str(day) for day in normalized)


def format_weekdays(days: tuple[int, ...] | list[int]) -> str:
    return ", ".join(DAY_NAMES[day] for day in sorted(set(days)))


def parse_time_range(value: str) -> tuple[int, int]:
    match = _TIME_RANGE_RE.fullmatch(value)
    if match is None:
        raise ValidationError("Введите время в формате 09:00–10:30.", field="time")
    start_hour, start_minute, end_hour, end_minute = (int(part) for part in match.groups())
    if start_hour > 23 or end_hour > 23 or start_minute > 59 or end_minute > 59:
        raise ValidationError("Проверьте часы и минуты.", field="time")
    start = start_hour * 60 + start_minute
    end = end_hour * 60 + end_minute
    if end <= start:
        raise ValidationError("Время окончания должно быть позже времени начала.", field="time")
    return start, end


def format_time_range(start_minute: int, end_minute: int) -> str:
    return (
        f"{start_minute // 60:02d}:{start_minute % 60:02d}–"
        f"{end_minute // 60:02d}:{end_minute % 60:02d}"
    )


def entries_overlap(first: ScheduleDraft, second: ScheduleDraft) -> bool:
    same_day = bool(set(first.weekdays) & set(second.weekdays))
    same_time = first.start_minute < second.end_minute and second.start_minute < first.end_minute
    return same_day and same_time


def entry_to_draft(entry: ScheduleEntry) -> ScheduleDraft:
    return ScheduleDraft(
        title=entry.title,
        weekdays=parse_weekdays(entry.weekdays),
        start_minute=entry.start_minute,
        end_minute=entry.end_minute,
    )


class ScheduleService:
    def __init__(self, session: AsyncSession) -> None:
        self._repository = ScheduleRepository(session)

    @staticmethod
    def validate_draft(
        title: str,
        weekdays: tuple[int, ...] | list[int],
        start_minute: int,
        end_minute: int,
    ) -> ScheduleDraft:
        clean_title = title.strip()
        if not clean_title:
            raise ValidationError("Название занятия не может быть пустым.", field="title")
        if len(clean_title) > 200:
            raise ValidationError("Название занятия слишком длинное.", field="title")
        normalized_days = tuple(sorted(set(weekdays)))
        serialize_weekdays(normalized_days)
        if not 0 <= start_minute < end_minute <= 1440:
            raise ValidationError("Некорректный интервал времени.", field="time")
        return ScheduleDraft(clean_title, normalized_days, start_minute, end_minute)

    async def list_entries(self, user_id: int) -> list[ScheduleEntry]:
        return await self._repository.list_for_user(user_id)

    async def get_entry(self, user_id: int, entry_id: int) -> ScheduleEntry:
        entry = await self._repository.get_for_user(user_id, entry_id)
        if entry is None:
            raise NotFound("Schedule entry", entry_id)
        return entry

    async def find_conflicts(
        self,
        user_id: int,
        draft: ScheduleDraft,
        exclude_id: int | None = None,
    ) -> list[ScheduleEntry]:
        entries = await self.list_entries(user_id)
        return [
            entry
            for entry in entries
            if entry.id != exclude_id and entries_overlap(draft, entry_to_draft(entry))
        ]

    async def save(
        self,
        user_id: int,
        draft: ScheduleDraft,
        entry_id: int | None = None,
    ) -> ScheduleEntry:
        if entry_id is None:
            return await self._repository.create(
                user_id,
                draft.title,
                serialize_weekdays(draft.weekdays),
                draft.start_minute,
                draft.end_minute,
            )
        entry = await self.get_entry(user_id, entry_id)
        entry.title = draft.title
        entry.weekdays = serialize_weekdays(draft.weekdays)
        entry.start_minute = draft.start_minute
        entry.end_minute = draft.end_minute
        return await self._repository.update(entry)

    async def replace_conflicts(
        self,
        user_id: int,
        draft: ScheduleDraft,
        entry_id: int | None = None,
    ) -> ScheduleEntry:
        conflicts = await self.find_conflicts(user_id, draft, exclude_id=entry_id)
        for conflict in conflicts:
            await self._repository.delete(conflict)
        return await self.save(user_id, draft, entry_id=entry_id)

    async def delete(self, user_id: int, entry_id: int) -> None:
        entry = await self.get_entry(user_id, entry_id)
        await self._repository.delete(entry)

