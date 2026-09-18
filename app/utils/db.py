from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_db_now(session: AsyncSession) -> datetime:
    return (await session.execute(text("SELECT now()"))).scalar_one()
