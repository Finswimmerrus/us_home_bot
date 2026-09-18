from __future__ import annotations

from datetime import datetime

from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import (
    InvalidStatusTransition,
    ValidationError,
)
from app.models.task import Task

VALID_STATUSES = ["TODO", "IN_PROGRESS", "DONE", "CANCELLED"]
VALID_PRIORITIES = ["LOW", "NORMAL", "HIGH"]
STATUS_TRANSITIONS = {
    "TODO": ["IN_PROGRESS", "DONE", "CANCELLED"],
    "IN_PROGRESS": ["TODO", "DONE", "CANCELLED"],
    "DONE": ["TODO", "IN_PROGRESS"],
    "CANCELLED": ["TODO", "IN_PROGRESS"],
}


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, task_id: int) -> Task | None:
        stmt = select(Task).where(Task.id == task_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_couple(
        self, couple_id: int, task_id: int
    ) -> Task | None:
        stmt = select(Task).where(
            Task.id == task_id, Task.couple_id == couple_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_for_couple(
        self,
        couple_id: int,
        status: str | None = None,
        assigned_to: int | None = None,
        created_by: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Task]:
        stmt = select(Task).where(Task.couple_id == couple_id)
        if status:
            stmt = stmt.where(Task.status == status)
        if assigned_to is not None:
            stmt = stmt.where(Task.assigned_to == assigned_to)
        if created_by is not None:
            stmt = stmt.where(Task.created_by == created_by)
        stmt = stmt.order_by(
            Task.due_at.asc().nullslast(), Task.created_at.desc()
        )
        if limit:
            stmt = stmt.limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_status_for_couple(
        self, couple_id: int, status: str
    ) -> list[Task]:
        stmt = (
            select(Task)
            .where(Task.couple_id == couple_id, Task.status == status)
            .order_by(Task.due_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        couple_id: int,
        created_by: int,
        title: str,
        description: str | None = None,
        priority: str = "NORMAL",
        assigned_to: int | None = None,
        due_at: datetime | None = None,
    ) -> Task:
        if priority not in VALID_PRIORITIES:
            raise ValidationError(f"Invalid priority: {priority}", field="priority")
        task = Task(
            couple_id=couple_id,
            created_by=created_by,
            assigned_to=assigned_to,
            title=title,
            description=description,
            status="TODO",
            priority=priority,
            due_at=due_at,
        )
        self._session.add(task)
        await self._session.flush()
        await self._session.refresh(task)
        return task

    async def update(self, task: Task) -> Task:
        self._session.add(task)
        await self._session.flush()
        await self._session.refresh(task)
        return task

    async def delete(self, task: Task) -> None:
        await self._session.delete(task)
        await self._session.flush()

    async def change_status(
        self, task: Task, new_status: str, user_id: int
    ) -> Task:
        if new_status not in VALID_STATUSES:
            raise ValidationError(f"Invalid status: {new_status}", field="status")
        allowed = STATUS_TRANSITIONS.get(task.status, [])
        if new_status not in allowed:
            raise InvalidStatusTransition(task.status, new_status, allowed)
        task.status = new_status
        if new_status == "DONE" and not task.completed_at:
            task.completed_at = datetime.utcnow()
            task.completed_by = user_id
        elif new_status != "DONE":
            task.completed_at = None
            task.completed_by = None
        return await self.update(task)

    async def assign(self, task: Task, user_id: int | None) -> Task:
        task.assigned_to = user_id
        return await self.update(task)

    async def get_due_today(
        self, couple_id: int, today: datetime
    ) -> list[Task]:
        stmt = select(Task).where(
            Task.couple_id == couple_id,
            Task.status != "DONE",
            cast(Task.due_at, Date) == cast(today, Date),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_upcoming(
        self, couple_id: int, limit: int = 5
    ) -> list[Task]:
        stmt = (
            select(Task)
            .where(
                Task.couple_id == couple_id,
                Task.status != "DONE",
                Task.due_at.is_not(None),
            )
            .order_by(Task.due_at.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_overdue(
        self, couple_id: int, now: datetime
    ) -> list[Task]:
        stmt = select(Task).where(
            Task.couple_id == couple_id,
            Task.status.notin_(["DONE", "CANCELLED"]),
            Task.due_at.is_not(None),
            Task.due_at < now,
        ).order_by(Task.due_at.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_status(self, couple_id: int) -> dict[str, int]:
        stmt = (
            select(Task.status, func.count(Task.id))
            .where(Task.couple_id == couple_id)
            .group_by(Task.status)
        )
        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}
