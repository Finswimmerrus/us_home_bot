import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import (
    NotFound,
    ValidationError,
)
from app.models.task import Task
from app.repositories.tasks import TaskRepository
from app.repositories.users import (
    CoupleMemberRepository,
    UserRepository,
)

logger = logging.getLogger(__name__)

VALID_STATUSES = ["TODO", "IN_PROGRESS", "DONE", "CANCELLED"]
VALID_PRIORITIES = ["LOW", "NORMAL", "HIGH"]


class TaskService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._task_repo = TaskRepository(session)
        self._user_repo = UserRepository(session)
        self._member_repo = CoupleMemberRepository(session)

    async def _validate_access(self, couple_id: int, user_id: int) -> None:
        await self._member_repo.validate_membership(couple_id, user_id)

    async def _validate_assignee(self, couple_id: int, user_id: int | None) -> None:
        if user_id is not None:
            await self._member_repo.validate_membership(couple_id, user_id)

    async def create_task(
        self,
        couple_id: int,
        created_by: int,
        title: str,
        description: str | None = None,
        priority: str = "NORMAL",
        assigned_to: int | None = None,
        due_at: datetime | None = None,
    ) -> Task:
        await self._validate_access(couple_id, created_by)
        await self._validate_assignee(couple_id, assigned_to)

        if not title or not title.strip():
            raise ValidationError("Task title cannot be empty", field="title")
        if priority not in VALID_PRIORITIES:
            raise ValidationError(f"Invalid priority: {priority}", field="priority")

        task = await self._task_repo.create(
            couple_id=couple_id,
            created_by=created_by,
            title=title.strip(),
            description=description,
            priority=priority,
            assigned_to=assigned_to,
            due_at=due_at,
        )
        logger.info("Created task id=%s in couple id=%s by user id=%s", task.id, couple_id, created_by)
        return task

    async def get_task(self, couple_id: int, user_id: int, task_id: int) -> Task:
        await self._validate_access(couple_id, user_id)
        task = await self._task_repo.get_for_couple(couple_id, task_id)
        if not task:
            raise NotFound("Task", task_id)
        return task

    async def get_all_tasks(
        self,
        couple_id: int,
        user_id: int,
        status: str | None = None,
        assigned_to: int | None = None,
        created_by: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Task]:
        await self._validate_access(couple_id, user_id)
        if assigned_to is not None:
            await self._validate_assignee(couple_id, assigned_to)
        if created_by is not None:
            await self._validate_assignee(couple_id, created_by)
        return await self._task_repo.get_all_for_couple(
            couple_id, status=status, assigned_to=assigned_to, created_by=created_by, limit=limit, offset=offset
        )

    async def get_tasks_by_status(self, couple_id: int, user_id: int, status: str) -> list[Task]:
        await self._validate_access(couple_id, user_id)
        if status not in VALID_STATUSES:
            raise ValidationError(f"Invalid status: {status}", field="status")
        return await self._task_repo.get_by_status_for_couple(couple_id, status)

    async def update_task(
        self,
        couple_id: int,
        user_id: int,
        task_id: int,
        title: str | None = None,
        description: str | None = None,
        priority: str | None = None,
        assigned_to: int | None = None,
        due_at: datetime | None = None,
    ) -> Task:
        await self._validate_access(couple_id, user_id)
        task = await self._task_repo.get_for_couple(couple_id, task_id)
        if not task:
            raise NotFound("Task", task_id)

        if assigned_to is not None:
            await self._validate_assignee(couple_id, assigned_to)

        if title is not None:
            if not title.strip():
                raise ValidationError("Task title cannot be empty", field="title")
            task.title = title.strip()
        if description is not None:
            task.description = description
        if priority is not None:
            if priority not in VALID_PRIORITIES:
                raise ValidationError(f"Invalid priority: {priority}", field="priority")
            task.priority = priority
        if assigned_to is not None:
            task.assigned_to = assigned_to
        if due_at is not None:
            task.due_at = due_at

        return await self._task_repo.update(task)

    async def change_status(self, couple_id: int, user_id: int, task_id: int, new_status: str) -> Task:
        await self._validate_access(couple_id, user_id)
        task = await self._task_repo.get_for_couple(couple_id, task_id)
        if not task:
            raise NotFound("Task", task_id)
        return await self._task_repo.change_status(task, new_status, user_id)

    async def assign_task(self, couple_id: int, user_id: int, task_id: int, assignee_id: int | None) -> Task:
        await self._validate_access(couple_id, user_id)
        if assignee_id is not None:
            await self._validate_assignee(couple_id, assignee_id)
        task = await self._task_repo.get_for_couple(couple_id, task_id)
        if not task:
            raise NotFound("Task", task_id)
        return await self._task_repo.assign(task, assignee_id)

    async def delete_task(self, couple_id: int, user_id: int, task_id: int) -> None:
        await self._validate_access(couple_id, user_id)
        task = await self._task_repo.get_for_couple(couple_id, task_id)
        if not task:
            raise NotFound("Task", task_id)
        await self._task_repo.delete(task)
        logger.info("Deleted task id=%s in couple id=%s by user id=%s", task_id, couple_id, user_id)

    async def get_today_tasks(self, couple_id: int, user_id: int) -> list[Task]:
        await self._validate_access(couple_id, user_id)
        return await self._task_repo.get_due_today(couple_id, datetime.utcnow())

    async def get_upcoming_tasks(self, couple_id: int, user_id: int, limit: int = 5) -> list[Task]:
        await self._validate_access(couple_id, user_id)
        return await self._task_repo.get_upcoming(couple_id, limit)

    async def get_overdue_tasks(self, couple_id: int, user_id: int) -> list[Task]:
        await self._validate_access(couple_id, user_id)
        return await self._task_repo.get_overdue(couple_id, datetime.utcnow())

    async def get_task_counts(self, couple_id: int, user_id: int) -> dict:
        await self._validate_access(couple_id, user_id)
        counts = await self._task_repo.count_by_status(couple_id)
        today = datetime.utcnow().date()
        active_tasks = await self._task_repo.get_by_status_for_couple(couple_id, "TODO")
        active_tasks += await self._task_repo.get_by_status_for_couple(couple_id, "IN_PROGRESS")
        due_today = [t for t in active_tasks if t.due_at and t.due_at.date() == today]
        return {
            "by_status": counts,
            "active": sum(counts.get(s, 0) for s in ["TODO", "IN_PROGRESS"]),
            "due_today": len(due_today),
            "total": sum(counts.values()),
        }
