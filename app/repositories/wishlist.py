from __future__ import annotations

from decimal import Decimal
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wishlist import WishlistItem
from app.exceptions import NotFound, ValidationError


VALID_WISHLIST_STATUSES = ["WANTED", "PURCHASED", "ARCHIVED"]


class WishlistRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, item_id: int) -> WishlistItem | None:
        stmt = select(WishlistItem).where(WishlistItem.id == item_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_couple(
        self, couple_id: int, item_id: int
    ) -> WishlistItem | None:
        stmt = select(WishlistItem).where(
            WishlistItem.id == item_id,
            WishlistItem.couple_id == couple_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_for_couple(
        self,
        couple_id: int,
        owner_id: int | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[WishlistItem]:
        stmt = select(WishlistItem).where(WishlistItem.couple_id == couple_id)
        if owner_id is not None:
            stmt = stmt.where(WishlistItem.owner_id == owner_id)
        if status:
            stmt = stmt.where(WishlistItem.status == status)
        stmt = stmt.order_by(WishlistItem.created_at.desc())
        if limit:
            stmt = stmt.limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        couple_id: int,
        owner_id: int,
        title: str,
        url: str | None = None,
        price: Decimal | None = None,
        description: str | None = None,
        status: str = "WANTED",
        priority: int = 0,
    ) -> WishlistItem:
        if not title or not title.strip():
            raise ValidationError(
                "Wishlist item title cannot be empty", field="title"
            )
        if price is not None and price < 0:
            raise ValidationError("Price cannot be negative", field="price")
        item = WishlistItem(
            couple_id=couple_id,
            owner_id=owner_id,
            title=title.strip(),
            url=url,
            price=price,
            description=description,
            status=status,
            priority=priority,
        )
        self._session.add(item)
        await self._session.flush()
        await self._session.refresh(item)
        return item

    async def update(self, item: WishlistItem) -> WishlistItem:
        self._session.add(item)
        await self._session.flush()
        await self._session.refresh(item)
        return item

    async def delete(self, item: WishlistItem) -> None:
        await self._session.delete(item)
        await self._session.flush()

    async def change_status(
        self, item: WishlistItem, new_status: str
    ) -> WishlistItem:
        if new_status not in VALID_WISHLIST_STATUSES:
            raise ValidationError(f"Invalid status: {new_status}", field="status")
        item.status = new_status
        return await self.update(item)

    async def get_counts_by_status(self, couple_id: int) -> dict[str, int]:
        stmt = (
            select(WishlistItem.status, func.count(WishlistItem.id))
            .where(WishlistItem.couple_id == couple_id)
            .group_by(WishlistItem.status)
        )
        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}