from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from aiogram.types import User as TelegramUser


@dataclass(slots=True)
class Context:
    user_id: int | None
    telegram_user: TelegramUser | None = None
    timezone: str = "UTC"
    couple_id: int | None = None
    is_creator: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def local_date(self) -> date:
        return datetime.now(ZoneInfo(self.timezone)).date()


def build_context(
    *,
    user_id: int | None,
    telegram_user: TelegramUser | None = None,
    timezone: str = "UTC",
    couple_id: int | None = None,
    is_creator: bool = False,
) -> Context:
    return Context(
        user_id=user_id,
        telegram_user=telegram_user,
        timezone=timezone,
        couple_id=couple_id,
        is_creator=is_creator,
    )
