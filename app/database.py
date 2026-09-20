from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import config


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    config.DATABASE_URL,
    echo=False,
)


@event.listens_for(engine.sync_engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
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


async def init_database() -> None:
    # Importing models registers every mapped table in Base.metadata.
    import app.models  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_lists_id_couple_id ON lists (id, couple_id)"
            )
        )
        for statement in (
            "DELETE FROM challenge_entries WHERE challenge_id NOT IN (SELECT id FROM challenges)",
            "DELETE FROM challenge_participants WHERE challenge_id NOT IN (SELECT id FROM challenges)",
            "DELETE FROM movie_ratings WHERE movie_id NOT IN (SELECT id FROM movies)",
            "DELETE FROM list_items WHERE list_id NOT IN (SELECT id FROM lists)",
            "DELETE FROM trip_places WHERE trip_id NOT IN (SELECT id FROM trips)",
            "DELETE FROM challenges WHERE couple_id NOT IN (SELECT id FROM couples)",
            "DELETE FROM tasks WHERE couple_id NOT IN (SELECT id FROM couples)",
            "DELETE FROM movie_ratings WHERE couple_id NOT IN (SELECT id FROM couples)",
            "DELETE FROM movies WHERE couple_id NOT IN (SELECT id FROM couples)",
            "DELETE FROM list_items WHERE couple_id NOT IN (SELECT id FROM couples)",
            "DELETE FROM lists WHERE couple_id NOT IN (SELECT id FROM couples)",
            "DELETE FROM trip_places WHERE couple_id NOT IN (SELECT id FROM couples)",
            "DELETE FROM trips WHERE couple_id NOT IN (SELECT id FROM couples)",
            "DELETE FROM wishlist_items WHERE couple_id NOT IN (SELECT id FROM couples)",
            "DELETE FROM notes WHERE couple_id NOT IN (SELECT id FROM couples)",
            "DELETE FROM couple_members WHERE couple_id NOT IN (SELECT id FROM couples)",
        ):
            await connection.execute(text(statement))


__all__ = ["Base", "engine", "SessionLocal", "get_session", "dispose_engine", "init_database"]
