from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aiogram.types import User as TelegramUser


@dataclass(slots=True)
class Context:
    user_id: int | None
    telegram_user: TelegramUser | None = None
    couple_id: int | None = None
    is_creator: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


def build_context(
    *,
    user_id: int | None,
    telegram_user: TelegramUser | None = None,
    couple_id: int | None = None,
    is_creator: bool = False,
) -> Context:
    return Context(
        user_id=user_id,
        telegram_user=telegram_user,
        couple_id=couple_id,
        is_creator=is_creator,
    )
