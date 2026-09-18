from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFound, ValidationError
from app.models.list import List as ListModel
from app.models.list_item import ListItem
from app.repositories.lists import ListItemRepository, ListRepository
from app.repositories.users import (
    CoupleMemberRepository,
    UserRepository,
)

logger = logging.getLogger(__name__)


class ListService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._list_repo = ListRepository(session)
        self._item_repo = ListItemRepository(session)
        self._user_repo = UserRepository(session)
        self._member_repo = CoupleMemberRepository(session)

    async def _validate_access(
        self, couple_id: int, user_id: int
    ) -> None:
        await self._member_repo.validate_membership(couple_id, user_id)

    async def _validate_list_access(
        self, couple_id: int, user_id: int, list_id: int
    ) -> ListModel:
        await self._validate_access(couple_id, user_id)
        lst = await self._list_repo.get_for_couple(couple_id, list_id)
        if lst is None:
            raise NotFound("List", list_id)
        return lst

    async def _validate_item_access(
        self,
        couple_id: int,
        user_id: int,
        list_id: int,
        item_id: int,
    ) -> ListItem:
        await self._validate_list_access(couple_id, user_id, list_id)
        item = await self._item_repo.get_by_id(item_id)
        if item is None or item.list_id != list_id:
            raise NotFound("ListItem", item_id)
        return item

    async def create_list(
        self, couple_id: int, user_id: int, name: str
    ) -> ListModel:
        await self._validate_access(couple_id, user_id)
        lst = await self._list_repo.create(couple_id, name, user_id)
        logger.info(
            "Created list id=%s in couple id=%s by user id=%s",
            lst.id, couple_id, user_id,
        )
        return lst

    async def get_list(
        self, couple_id: int, user_id: int, list_id: int
    ) -> ListModel:
        return await self._validate_list_access(couple_id, user_id, list_id)

    async def get_all_lists(
        self,
        couple_id: int,
        user_id: int,
        created_by: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ListModel]:
        await self._validate_access(couple_id, user_id)
        if created_by is not None:
            await self._member_repo.validate_membership(
                couple_id, created_by
            )
        return await self._list_repo.get_all_for_couple(
            couple_id,
            created_by=created_by,
            limit=limit,
            offset=offset,
        )

    async def update_list(
        self, couple_id: int, user_id: int, list_id: int, name: str
    ) -> ListModel:
        lst = await self._validate_list_access(couple_id, user_id, list_id)
        if not name or not name.strip():
            raise ValidationError("List name cannot be empty", field="name")
        lst.name = name.strip()
        return await self._list_repo.update(lst)

    async def delete_list(
        self, couple_id: int, user_id: int, list_id: int
    ) -> None:
        lst = await self._validate_list_access(couple_id, user_id, list_id)
        await self._list_repo.delete(lst)
        logger.info(
            "Deleted list id=%s in couple id=%s by user id=%s",
            list_id, couple_id, user_id,
        )

    async def add_item(
        self, couple_id: int, user_id: int, list_id: int, title: str
    ) -> ListItem:
        await self._validate_list_access(couple_id, user_id, list_id)
        if not title or not title.strip():
            raise ValidationError(
                "Item title cannot be empty", field="title"
            )
        item = await self._item_repo.create(
            list_id, title.strip(), user_id
        )
        logger.info(
            "Added item id=%s to list id=%s by user id=%s",
            item.id, list_id, user_id,
        )
        return item

    async def get_items(
        self,
        couple_id: int,
        user_id: int,
        list_id: int,
        include_completed: bool = True,
    ) -> list[ListItem]:
        await self._validate_list_access(couple_id, user_id, list_id)
        return await self._item_repo.get_for_list(
            list_id, include_completed=include_completed
        )

    async def get_active_items(
        self, couple_id: int, user_id: int, list_id: int
    ) -> list[ListItem]:
        await self._validate_list_access(couple_id, user_id, list_id)
        return await self._item_repo.get_active_for_list(list_id)

    async def get_completed_items(
        self, couple_id: int, user_id: int, list_id: int
    ) -> list[ListItem]:
        await self._validate_list_access(couple_id, user_id, list_id)
        return await self._item_repo.get_completed_for_list(list_id)

    async def complete_item(
        self,
        couple_id: int,
        user_id: int,
        list_id: int,
        item_id: int,
    ) -> ListItem:
        item = await self._validate_item_access(
            couple_id, user_id, list_id, item_id
        )
        return await self._item_repo.complete(item, user_id)

    async def uncomplete_item(
        self,
        couple_id: int,
        user_id: int,
        list_id: int,
        item_id: int,
    ) -> ListItem:
        item = await self._validate_item_access(
            couple_id, user_id, list_id, item_id
        )
        return await self._item_repo.uncomplete(item)

    async def update_item(
        self,
        couple_id: int,
        user_id: int,
        list_id: int,
        item_id: int,
        title: str,
    ) -> ListItem:
        item = await self._validate_item_access(
            couple_id, user_id, list_id, item_id
        )
        if not title or not title.strip():
            raise ValidationError(
                "Item title cannot be empty", field="title"
            )
        item.title = title.strip()
        return await self._item_repo.update(item)

    async def delete_item(
        self,
        couple_id: int,
        user_id: int,
        list_id: int,
        item_id: int,
    ) -> None:
        item = await self._validate_item_access(
            couple_id, user_id, list_id, item_id
        )
        await self._item_repo.delete(item)
        logger.info(
            "Deleted item id=%s from list id=%s by user id=%s",
            item_id, list_id, user_id,
        )

    async def clear_completed(
        self, couple_id: int, user_id: int, list_id: int
    ) -> int:
        await self._validate_list_access(couple_id, user_id, list_id)
        count = await self._item_repo.clear_completed(list_id)
        logger.info(
            "Cleared %d completed items from list id=%s by user id=%s",
            count, list_id, user_id,
        )
        return count

    async def get_counts(
        self, couple_id: int, user_id: int, list_id: int
    ) -> dict[str, int]:
        await self._validate_list_access(couple_id, user_id, list_id)
        return await self._item_repo.get_counts(list_id)
