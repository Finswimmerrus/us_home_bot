from __future__ import annotations

import logging
import zoneinfo
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.users import CoupleMemberRepository
from app.repositories.settings import SettingsRepository
from app.exceptions import NotFound, Forbidden, ValidationError

logger = logging.getLogger(__name__)


class SettingsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._settings_repo = SettingsRepository(session)
        self._member_repo = CoupleMemberRepository(session)

    async def _validate_access(
        self, couple_id: int, user_id: int
    ) -> None:
        await self._member_repo.validate_membership(couple_id, user_id)

    async def get_user_settings(self, user_id: int) -> dict:
        return await self._settings_repo.get_user_settings(user_id)

    async def update_user_display_name(
        self, user_id: int, display_name: str
    ) -> bool:
        if not display_name or not display_name.strip():
            raise ValidationError(
                "Display name cannot be empty", field="display_name"
            )
        return await self._settings_repo.set_user_display_name(
            user_id, display_name.strip()
        )

    async def get_user_timezone(self, user_id: int) -> str:
        return await self._settings_repo.get_user_timezone(user_id)

    async def set_user_timezone(
        self, user_id: int, timezone: str
    ) -> bool:
        try:
            zoneinfo.ZoneInfo(timezone)
        except Exception:
            raise ValidationError(
                f"Invalid IANA timezone: {timezone}", field="timezone"
            )
        return await self._settings_repo.set_user_timezone(
            user_id, timezone
        )

    async def get_couple_settings(
        self, couple_id: int, user_id: int
    ) -> dict:
        await self._validate_access(couple_id, user_id)
        return await self._settings_repo.get_couple_settings(couple_id)

    async def update_couple_name(
        self, couple_id: int, user_id: int, name: str
    ) -> bool:
        await self._validate_access(couple_id, user_id)
        if not name or not name.strip():
            raise ValidationError(
                "Couple name cannot be empty", field="name"
            )
        return await self._settings_repo.set_couple_name(
            couple_id, name.strip()
        )

    async def get_couple_name(
        self, couple_id: int, user_id: int
    ) -> str | None:
        await self._validate_access(couple_id, user_id)
        return await self._settings_repo.get_couple_name(couple_id)