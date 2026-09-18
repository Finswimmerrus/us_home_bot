from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import Forbidden
from app.models.couple import Couple
from app.models.couple_member import CoupleMember
from app.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: int) -> User | None:
        stmt = select(User).where(User.id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
    ) -> User:
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
        )
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)
        return user

    async def update(self, user: User) -> User:
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)
        return user

    async def delete(self, user: User) -> None:
        await self._session.delete(user)
        await self._session.flush()


class CoupleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, couple_id: int) -> Couple | None:
        stmt = select(Couple).where(Couple.id == couple_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_invite_code(self, code: str) -> Couple | None:
        stmt = select(Couple).where(Couple.invite_code == code)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        name: str,
        invite_code: str,
        invite_expires_at: datetime | None = None,
    ) -> Couple:
        couple = Couple(
            name=name,
            invite_code=invite_code,
            invite_expires_at=invite_expires_at,
        )
        self._session.add(couple)
        await self._session.flush()
        await self._session.refresh(couple)
        return couple

    async def update(self, couple: Couple) -> Couple:
        self._session.add(couple)
        await self._session.flush()
        await self._session.refresh(couple)
        return couple

    async def delete(self, couple: Couple) -> None:
        await self._session.delete(couple)
        await self._session.flush()

    async def get_for_user(self, user_id: int) -> Couple | None:
        stmt = (
            select(Couple)
            .join(CoupleMember, CoupleMember.couple_id == Couple.id)
            .where(CoupleMember.user_id == user_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


class CoupleMemberRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def is_member(self, couple_id: int, user_id: int) -> bool:
        stmt = select(CoupleMember).where(
            CoupleMember.couple_id == couple_id,
            CoupleMember.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def add(self, couple_id: int, user_id: int) -> CoupleMember:
        member = CoupleMember(couple_id=couple_id, user_id=user_id)
        self._session.add(member)
        await self._session.flush()
        await self._session.refresh(member)
        return member

    async def get_member_user_ids(self, couple_id: int) -> list[int]:
        stmt = select(CoupleMember.user_id).where(CoupleMember.couple_id == couple_id)
        result = await self._session.execute(stmt)
        return [row[0] for row in result.all()]

    async def get_members(self, couple_id: int) -> list[CoupleMember]:
        stmt = select(CoupleMember).where(CoupleMember.couple_id == couple_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_couple_for_user(self, user_id: int) -> Couple | None:
        stmt = (
            select(Couple)
            .join(CoupleMember, CoupleMember.couple_id == Couple.id)
            .where(CoupleMember.user_id == user_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def remove_member(self, couple_id: int, user_id: int) -> bool:
        stmt = select(CoupleMember).where(
            CoupleMember.couple_id == couple_id,
            CoupleMember.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        member = result.scalar_one_or_none()
        if member is None:
            return False
        await self._session.delete(member)
        await self._session.flush()
        return True

    async def count_members(self, couple_id: int) -> int:
        stmt = select(func.count(CoupleMember.id)).where(
            CoupleMember.couple_id == couple_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def validate_membership(self, couple_id: int, user_id: int) -> None:
        if not await self.is_member(couple_id, user_id):
            raise Forbidden(
                "access couple resources",
                {"couple_id": couple_id, "user_id": user_id},
            )
