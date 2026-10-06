from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schedule import ScheduleEntry


class ScheduleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_couple(self, couple_id: int) -> list[ScheduleEntry]:
        result = await self._session.execute(
            select(ScheduleEntry)
            .where(ScheduleEntry.couple_id == couple_id)
            .order_by(ScheduleEntry.start_minute, ScheduleEntry.title)
        )
        return list(result.scalars().all())

    async def get_for_couple(self, couple_id: int, entry_id: int) -> ScheduleEntry | None:
        result = await self._session.execute(
            select(ScheduleEntry).where(
                ScheduleEntry.id == entry_id,
                ScheduleEntry.couple_id == couple_id,
            )
        )
        entry: ScheduleEntry | None = result.scalar_one_or_none()
        return entry

    async def create(
        self,
        couple_id: int,
        created_by: int,
        title: str,
        weekdays: str,
        start_minute: int,
        end_minute: int,
    ) -> ScheduleEntry:
        entry = ScheduleEntry(
            couple_id=couple_id,
            user_id=created_by,
            title=title,
            weekdays=weekdays,
            start_minute=start_minute,
            end_minute=end_minute,
        )
        self._session.add(entry)
        await self._session.flush()
        await self._session.refresh(entry)
        return entry

    async def update(self, entry: ScheduleEntry) -> ScheduleEntry:
        self._session.add(entry)
        await self._session.flush()
        await self._session.refresh(entry)
        return entry

    async def delete(self, entry: ScheduleEntry) -> None:
        await self._session.delete(entry)
        await self._session.flush()
