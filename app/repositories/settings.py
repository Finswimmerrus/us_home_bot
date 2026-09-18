from __future__ import annotations

import zoneinfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ValidationError
from app.models.couple import Couple
from app.models.user import User


class SettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_couple_name(self, couple_id: int) -> str | None:
        stmt = select(Couple.name).where(Couple.id == couple_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def set_couple_name(self, couple_id: int, name: str) -> bool:
        if not name or not name.strip():
            raise ValidationError("Couple name cannot be empty", field="name")
        couple = await self._get_couple(couple_id)
        if couple is None:
            return False
        couple.name = name.strip()
        self._session.add(couple)
        await self._session.flush()
        return True

    async def get_user_display_name(self, user_id: int) -> str | None:
        user = await self._get_user(user_id)
        if user is None:
            return None
        if user.display_name:
            return user.display_name
        return user.first_name or user.username

    async def set_user_display_name(self, user_id: int, display_name: str) -> bool:
        if not display_name or not display_name.strip():
            raise ValidationError(
                "Display name cannot be empty", field="display_name"
            )
        user = await self._get_user(user_id)
        if user is None:
            return False
        user.display_name = display_name.strip()
        self._session.add(user)
        await self._session.flush()
        return True

    async def get_user_timezone(self, user_id: int) -> str:
        from app.config import config

        user = await self._get_user(user_id)
        if user is not None and user.timezone:
            return user.timezone
        return config.DEFAULT_TIMEZONE

    async def set_user_timezone(self, user_id: int, timezone: str) -> bool:
        try:
            zoneinfo.ZoneInfo(timezone)
        except Exception as exc:
            raise ValidationError(
                f"Invalid IANA timezone: {timezone}", field="timezone"
            ) from exc
        user = await self._get_user(user_id)
        if user is None:
            return False
        user.timezone = timezone
        self._session.add(user)
        await self._session.flush()
        return True

    async def get_user_settings(self, user_id: int) -> dict:
        from app.config import config

        user = await self._get_user(user_id)
        if user is None:
            return {}
        return {
            "display_name": (
                user.display_name or user.first_name or user.username
            ),
            "timezone": user.timezone or config.DEFAULT_TIMEZONE,
            "username": user.username,
            "first_name": user.first_name,
        }

    async def get_couple_settings(self, couple_id: int) -> dict:
        couple = await self._get_couple(couple_id)
        if couple is None:
            return {}
        return {
            "name": couple.name,
            "invite_code": couple.invite_code,
            "invite_expires_at": couple.invite_expires_at,
        }

    async def _get_user(self, user_id: int) -> User | None:
        stmt = select(User).where(User.id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_couple(self, couple_id: int) -> Couple | None:
        stmt = select(Couple).where(Couple.id == couple_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
