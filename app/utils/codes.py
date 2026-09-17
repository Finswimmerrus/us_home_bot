from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta, timezone


def generate_invite_code() -> str:
    letters = "".join(secrets.choice(string.ascii_uppercase) for _ in range(4))
    digits = "".join(secrets.choice(string.digits) for _ in range(4))
    return f"{letters}-{digits}"


def invite_code_expires(hours: int = 48) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def is_invite_expired(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return True
    value = expires_at
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value < datetime.now(timezone.utc)
