import logging
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFound, ValidationError
from app.repositories.users import CoupleMemberRepository
from app.repositories.wishlist import WishlistRepository

logger = logging.getLogger(__name__)

VALID_WISHLIST_STATUSES = ["WANTED", "PURCHASED", "ARCHIVED"]


class WishlistService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._wishlist_repo = WishlistRepository(session)
        self._member_repo = CoupleMemberRepository(session)

    async def _validate_access(self, couple_id: int, user_id: int) -> None:
        await self._member_repo.validate_membership(couple_id, user_id)

    async def _validate_item_access(
        self, couple_id: int, user_id: int, item_id: int
    ) -> Any:
        await self._validate_access(couple_id, user_id)
        item = await self._wishlist_repo.get_for_couple(couple_id, item_id)
        if item is None:
            raise NotFound("WishlistItem", item_id)
        return item

    async def add_item(
        self,
        couple_id: int,
        user_id: int,
        title: str,
        url: str | None = None,
        price: Decimal | float | str | None = None,
        description: str | None = None,
        status: str = "WANTED",
    ) -> Any:
        await self._validate_access(couple_id, user_id)
        if status not in VALID_WISHLIST_STATUSES:
            raise ValidationError(f"Invalid status: {status}", field="status")
        if price is not None:
            price = Decimal(str(price))
            if price < 0:
                raise ValidationError("Price cannot be negative", field="price")

        item = await self._wishlist_repo.create(
            couple_id=couple_id,
            owner_id=user_id,
            title=title,
            url=url,
            price=price,
            description=description,
            status=status,
        )
        logger.info("Added wishlist item id=%s to couple id=%s by user id=%s", item.id, couple_id, user_id)
        return item

    async def get_item(self, couple_id: int, user_id: int, item_id: int) -> Any:
        return await self._validate_item_access(couple_id, user_id, item_id)

    async def get_all_items(
        self,
        couple_id: int,
        user_id: int,
        owner_id: int | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Any]:
        await self._validate_access(couple_id, user_id)
        if owner_id is not None:
            await self._member_repo.validate_membership(couple_id, owner_id)
        if status and status not in VALID_WISHLIST_STATUSES:
            raise ValidationError(f"Invalid status: {status}", field="status")
        return await self._wishlist_repo.get_all_for_couple(
            couple_id,
            owner_id=owner_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def update_item(
        self,
        couple_id: int,
        user_id: int,
        item_id: int,
        title: str | None = None,
        url: str | None = None,
        price: Decimal | float | str | None = None,
        description: str | None = None,
    ) -> Any:
        item = await self._validate_item_access(couple_id, user_id, item_id)

        if title is not None:
            if not title.strip():
                raise ValidationError("Item title cannot be empty", field="title")
            item.title = title.strip()
        if url is not None:
            item.url = url
        if price is not None:
            price = Decimal(str(price))
            if price < 0:
                raise ValidationError("Price cannot be negative", field="price")
            item.price = price
        if description is not None:
            item.description = description

        return await self._wishlist_repo.update(item)

    async def change_status(
        self,
        couple_id: int,
        user_id: int,
        item_id: int,
        new_status: str,
    ) -> Any:
        item = await self._validate_item_access(couple_id, user_id, item_id)
        if new_status not in VALID_WISHLIST_STATUSES:
            raise ValidationError(f"Invalid status: {new_status}", field="status")
        return await self._wishlist_repo.change_status(item, new_status)

    async def delete_item(self, couple_id: int, user_id: int, item_id: int) -> None:
        item = await self._validate_item_access(couple_id, user_id, item_id)
        await self._wishlist_repo.delete(item)
        logger.info("Deleted wishlist item id=%s from couple id=%s by user id=%s", item_id, couple_id, user_id)

    async def get_counts_by_status(self, couple_id: int, user_id: int) -> dict[str, int]:
        await self._validate_access(couple_id, user_id)
        return await self._wishlist_repo.get_counts_by_status(couple_id)

    async def get_items_by_owner(
        self, couple_id: int, user_id: int, owner_id: int
    ) -> list[Any]:
        await self._validate_access(couple_id, user_id)
        await self._member_repo.validate_membership(couple_id, owner_id)
        return await self._wishlist_repo.get_all_for_couple(couple_id, owner_id=owner_id)
