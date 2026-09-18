from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import (
    Conflict,
    CoupleFull,
    NotFound,
    ValidationError,
)
from app.models.couple import Couple
from app.models.couple_member import CoupleMember
from app.models.user import User
from app.repositories.users import (
    CoupleMemberRepository,
    CoupleRepository,
    UserRepository,
)
from app.utils.codes import generate_invite_code, invite_code_expires

logger = logging.getLogger(__name__)


class CoupleService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._user_repo = UserRepository(session)
        self._couple_repo = CoupleRepository(session)
        self._member_repo = CoupleMemberRepository(session)

    async def get_or_create_user(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
    ) -> User:
        user = await self._user_repo.get_by_telegram_id(telegram_id)
        if user is None:
            user = await self._user_repo.create(telegram_id, username, first_name)
            logger.info("Created user telegram_id=%s", telegram_id)
            return user

        updated = False
        if username and user.username != username:
            user.username = username
            updated = True
        if first_name and user.first_name != first_name:
            user.first_name = first_name
            updated = True
        if updated:
            await self._user_repo.update(user)
        return user

    async def create_couple(
        self, user: User, name: str = "Наша пара"
    ) -> tuple[Couple, CoupleMember]:
        if await self.get_user_couple(user.id) is not None:
            raise Conflict("Вы уже состоите в паре.")
        if not name or not name.strip():
            raise ValidationError("Couple name cannot be empty", field="name")
        invite_code = generate_invite_code()
        expires_at = invite_code_expires()
        couple = await self._couple_repo.create(
            name.strip(), invite_code, expires_at
        )
        member = await self._member_repo.add(couple.id, user.id)
        logger.info(
            "Created couple id=%s by user id=%s", couple.id, user.id
        )
        return couple, member

    async def find_couple_by_code(self, code: str) -> Couple | None:
        couple = await self._couple_repo.get_by_invite_code(code)
        if couple is None:
            return None
        if is_invite_expired(couple.invite_expires_at):
            return None
        return couple

    async def join_couple(
        self, user: User, couple: Couple
    ) -> CoupleMember | None:
        current_couple = await self.get_user_couple(user.id)
        if current_couple is not None and current_couple.id != couple.id:
            raise Conflict("Вы уже состоите в другой паре.")

        member_count = await self._member_repo.count_members(couple.id)
        if member_count >= 2:
            raise CoupleFull(couple.id)

        if await self._member_repo.is_member(couple.id, user.id):
            return None

        member = await self._member_repo.add(couple.id, user.id)
        couple.invite_code = None
        couple.invite_expires_at = None
        await self._couple_repo.update(couple)
        logger.info(
            "User id=%s joined couple id=%s", user.id, couple.id
        )
        return member

    async def get_user_couple(self, user_id: int) -> Couple | None:
        return await self._member_repo.get_couple_for_user(user_id)

    async def get_couple_members(self, couple_id: int) -> list[User]:
        stmt = (
            select(User)
            .join(CoupleMember, CoupleMember.user_id == User.id)
            .where(CoupleMember.couple_id == couple_id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_other_member(
        self, couple_id: int, user_id: int
    ) -> User | None:
        members = await self.get_couple_members(couple_id)
        for member in members:
            if member.id != user_id:
                return member
        return None

    async def leave_couple(self, couple_id: int, user_id: int) -> bool:
        await self._member_repo.validate_membership(couple_id, user_id)
        member_count = await self._member_repo.count_members(couple_id)
        if member_count <= 1:
            raise Conflict(
                "Cannot leave couple: you are the only member. "
                "Delete the couple instead."
            )
        return await self._member_repo.remove_member(couple_id, user_id)

    async def delete_couple(self, couple_id: int, user_id: int) -> bool:
        await self._member_repo.validate_membership(couple_id, user_id)
        couple = await self._couple_repo.get_by_id(couple_id)
        if couple is None:
            return False
        await self._couple_repo.delete(couple)
        logger.info(
            "Deleted couple id=%s by user id=%s", couple_id, user_id
        )
        return True

    async def update_couple_name(
        self, couple_id: int, user_id: int, name: str
    ) -> Couple:
        await self._member_repo.validate_membership(couple_id, user_id)
        if not name or not name.strip():
            raise ValidationError("Couple name cannot be empty", field="name")
        couple = await self._couple_repo.get_by_id(couple_id)
        if couple is None:
            raise NotFound("Couple", couple_id)
        couple.name = name.strip()
        return await self._couple_repo.update(couple)

    async def regenerate_invite_code(
        self, couple_id: int, user_id: int
    ) -> str:
        await self._member_repo.validate_membership(couple_id, user_id)
        couple = await self._couple_repo.get_by_id(couple_id)
        if couple is None:
            raise NotFound("Couple", couple_id)
        if couple.member_count >= 2:
            raise Conflict(
                "Cannot regenerate invite code: couple is already full"
            )
        new_code = generate_invite_code()
        couple.invite_code = new_code
        couple.invite_expires_at = invite_code_expires()
        await self._couple_repo.update(couple)
        logger.info(
            "Regenerated invite code for couple id=%s", couple_id
        )
        return new_code


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._couple_service = CoupleService(session)
        self._user_repo = UserRepository(session)

    async def handle_start(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
    ) -> dict:
        user = await self._couple_service.get_or_create_user(
            telegram_id, username, first_name
        )
        couple = await self._couple_service.get_user_couple(user.id)
        return {
            "user": user,
            "couple": couple,
            "has_couple": couple is not None,
        }

    async def get_user_profile(self, user_id: int) -> User | None:
        return await self._user_repo.get_by_id(user_id)

    async def update_user_profile(
        self,
        user_id: int,
        username: str | None = None,
        first_name: str | None = None,
    ) -> User | None:
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            return None
        if username is not None:
            user.username = username
        if first_name is not None:
            user.first_name = first_name
        return await self._user_repo.update(user)


def is_invite_expired(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return True
    value = expires_at
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value < datetime.now(UTC)
