from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.database import Base, ensure_runtime_schema
from app.exceptions import ValidationError
from app.models.couple import Couple
from app.models.user import User
from app.services.schedule_service import (
    ScheduleDraft,
    ScheduleService,
    entries_overlap,
    format_time_range,
    parse_time_range,
)


def test_parse_and_format_time_range() -> None:
    assert parse_time_range("9:05 - 10:30") == (545, 630)
    assert parse_time_range("18:00–19:15") == (1080, 1155)
    assert format_time_range(545, 630) == "09:05–10:30"


@pytest.mark.parametrize("value", ["09:00", "25:00-26:00", "12:00-11:00", "text"])
def test_reject_invalid_time_range(value: str) -> None:
    with pytest.raises(ValidationError):
        parse_time_range(value)


def test_overlap_requires_common_day_and_time() -> None:
    monday_yoga = ScheduleDraft("Йога", (0,), 18 * 60, 19 * 60)
    overlapping = ScheduleDraft("Ужин", (0, 2), 18 * 60 + 30, 20 * 60)
    adjacent = ScheduleDraft("Прогулка", (0,), 19 * 60, 20 * 60)
    another_day = ScheduleDraft("Ужин", (1,), 18 * 60 + 30, 20 * 60)

    assert entries_overlap(monday_yoga, overlapping)
    assert not entries_overlap(monday_yoga, adjacent)
    assert not entries_overlap(monday_yoga, another_day)


async def test_replace_conflicting_entry() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        user = User(telegram_id=12345)
        partner = User(telegram_id=67890)
        couple = Couple(name="Общая пара")
        session.add_all([user, partner, couple])
        await session.flush()
        service = ScheduleService(session)
        yoga = ScheduleDraft("Йога", (0, 2), 18 * 60, 19 * 60)
        dinner = ScheduleDraft("Ужин", (0,), 18 * 60 + 30, 20 * 60)

        await service.save(couple.id, user.id, yoga)
        conflicts = await service.find_conflicts(couple.id, dinner)
        assert [entry.title for entry in conflicts] == ["Йога"]
        assert [entry.title for entry in await service.list_entries(couple.id)] == ["Йога"]

        await service.replace_conflicts(couple.id, partner.id, dinner)
        entries = await service.list_entries(couple.id)
        assert [entry.title for entry in entries] == ["Ужин"]

    await engine.dispose()


async def test_legacy_schedule_is_migrated_to_couple() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        for statement in (
            "CREATE TABLE couples (id INTEGER PRIMARY KEY)",
            "CREATE TABLE users (id INTEGER PRIMARY KEY)",
            "CREATE TABLE couple_members (id INTEGER PRIMARY KEY, couple_id INTEGER, user_id INTEGER)",
            "CREATE TABLE schedule_entries (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL)",
            "INSERT INTO couples (id) VALUES (10)",
            "INSERT INTO users (id) VALUES (20)",
            "INSERT INTO couple_members (id, couple_id, user_id) VALUES (1, 10, 20)",
            "INSERT INTO schedule_entries (id, user_id) VALUES (1, 20)",
        ):
            await connection.execute(text(statement))

        await ensure_runtime_schema(connection)
        result = await connection.execute(
            text("SELECT couple_id FROM schedule_entries WHERE id = 1")
        )
        assert result.scalar_one() == 10

    await engine.dispose()
