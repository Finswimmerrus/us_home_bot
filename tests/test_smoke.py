from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import inspect

from app.database import SessionLocal, engine, init_database
from app.handlers.crud import router as crud_router
from app.services.challenge_service import ChallengeService
from app.services.couple_service import CoupleService


async def test_database_schema_and_crud_router_are_available() -> None:
    await init_database()
    async with engine.connect() as connection:
        table_names = await connection.run_sync(
            lambda sync_connection: set(inspect(sync_connection).get_table_names())
        )

    assert {"users", "couples", "tasks", "movies", "lists", "challenges"} <= table_names
    assert crud_router.message.handlers
    assert crud_router.callback_query.handlers


async def test_challenge_savings_stats_and_entry_update() -> None:
    await init_database()
    async with SessionLocal() as session:
        couple_service = CoupleService(session)
        suffix = uuid4().int % 1_000_000_000
        user = await couple_service.get_or_create_user(
            telegram_id=910_000_000_000 + suffix,
            username="challenge_user",
            first_name="Tester",
        )
        couple, _ = await couple_service.create_couple(user, name=f"Challenge {suffix}")
        service = ChallengeService(session)
        start = date.today() - timedelta(days=1)
        challenge = await service.create_challenge(
            couple.id,
            user.id,
            "Не покупать кофе",
            "PERSONAL",
            "SAVINGS",
            start,
            date.today() + timedelta(days=3),
            Decimal("300"),
        )

        await service.record_entry(couple.id, user.id, challenge.id, start, "SUCCESS")
        await service.record_entry(
            couple.id,
            user.id,
            challenge.id,
            date.today(),
            "MISSED",
            Decimal("120"),
        )
        await service.record_entry(
            couple.id,
            user.id,
            challenge.id,
            date.today(),
            "MISSED",
            Decimal("150"),
        )
        challenge = await service.get_challenge(couple.id, user.id, challenge.id)
        stats = ChallengeService.calculate_stats(challenge, date.today())

    assert len(challenge.entries) == 2
    assert stats.expected_amount_to_date == Decimal("600.00")
    assert stats.actual_spending == Decimal("150.00")
    assert stats.calculated_savings == Decimal("450.00")
