from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import config


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    config.DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
)
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def dispose_engine() -> None:
    await engine.dispose()


__all__ = ["Base", "engine", "SessionLocal", "get_session", "dispose_engine"]
