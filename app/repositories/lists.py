from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFound, ValidationError
from app.models.list import List as ListModel
from app.models.list_item import ListItem


class ListRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, list_id: int) -> ListModel | None:
        stmt = select(ListModel).where(ListModel.id == list_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_couple(
        self, couple_id: int, list_id: int
    ) -> ListModel | None:
        stmt = select(ListModel).where(
            ListModel.id == list_id, ListModel.couple_id == couple_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_for_couple(
        self,
        couple_id: int,
        created_by: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ListModel]:
        stmt = select(ListModel).where(ListModel.couple_id == couple_id)
        if created_by is not None:
            stmt = stmt.where(ListModel.created_by == created_by)
        stmt = stmt.order_by(ListModel.created_at.desc())
        if limit:
            stmt = stmt.limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self, couple_id: int, name: str, created_by: int
    ) -> ListModel:
        if not name or not name.strip():
            raise ValidationError("List name cannot be empty", field="name")
        lst = ListModel(
            couple_id=couple_id,
            name=name.strip(),
            created_by=created_by,
        )
        self._session.add(lst)
        await self._session.flush()
        await self._session.refresh(lst)
        return lst

    async def update(self, lst: ListModel) -> ListModel:
        self._session.add(lst)
        await self._session.flush()
        await self._session.refresh(lst)
        return lst

    async def delete(self, lst: ListModel) -> None:
        await self._session.delete(lst)
        await self._session.flush()


class ListItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, item_id: int) -> ListItem | None:
        stmt = select(ListItem).where(ListItem.id == item_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_list(
        self, list_id: int, include_completed: bool = True
    ) -> list[ListItem]:
        stmt = select(ListItem).where(ListItem.list_id == list_id).order_by(
            ListItem.completed_at.asc().nullslast(),
            ListItem.created_at.asc(),
        )
        result = await self._session.execute(stmt)
        items = list(result.scalars().all())
        if not include_completed:
            items = [i for i in items if i.completed_at is None]
        return items

    async def get_active_for_list(self, list_id: int) -> list[ListItem]:
        return await self.get_for_list(list_id, include_completed=False)

    async def get_completed_for_list(self, list_id: int) -> list[ListItem]:
        stmt = (
            select(ListItem)
            .where(
                ListItem.list_id == list_id,
                ListItem.completed_at.is_not(None),
            )
            .order_by(ListItem.completed_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self, list_id: int, title: str, created_by: int
    ) -> ListItem:
        if not title or not title.strip():
            raise ValidationError("Item title cannot be empty", field="title")
        parent = await self._session.get(ListModel, list_id)
        if parent is None:
            raise NotFound("List", list_id)
        item = ListItem(
            couple_id=parent.couple_id,
            list_id=list_id,
            title=title.strip(),
            created_by=created_by,
        )
        self._session.add(item)
        await self._session.flush()
        await self._session.refresh(item)
        return item

    async def complete(self, item: ListItem, completed_by: int) -> ListItem:
        item.completed_by = completed_by
        item.completed_at = datetime.now(UTC)
        self._session.add(item)
        await self._session.flush()
        await self._session.refresh(item)
        return item

    async def uncomplete(self, item: ListItem) -> ListItem:
        item.completed_by = None
        item.completed_at = None
        self._session.add(item)
        await self._session.flush()
        await self._session.refresh(item)
        return item

    async def update(self, item: ListItem) -> ListItem:
        self._session.add(item)
        await self._session.flush()
        await self._session.refresh(item)
        return item

    async def delete(self, item: ListItem) -> None:
        await self._session.delete(item)
        await self._session.flush()

    async def clear_completed(self, list_id: int) -> int:
        stmt = select(ListItem).where(
            ListItem.list_id == list_id,
            ListItem.completed_at.is_not(None),
        )
        result = await self._session.execute(stmt)
        items = list(result.scalars().all())
        for item in items:
            await self._session.delete(item)
        await self._session.flush()
        return len(items)

    async def get_counts(self, list_id: int) -> dict[str, int]:
        stmt = select(
            func.count(ListItem.id),
            func.count(ListItem.completed_at),
        ).where(ListItem.list_id == list_id)
        result = await self._session.execute(stmt)
        total, completed = result.one()
        return {
            "total": total,
            "completed": completed,
            "active": total - completed,
        }
