from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import inspect

from app.database import SessionLocal, engine, init_database
from app.exceptions import ValidationError
from app.handlers.crud import router as crud_router
from app.handlers.start import _invite_message
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


def test_invite_message_is_self_contained() -> None:
    text = _invite_message("Наша пара", "ABCD-1234", "couple_test_bot")

    assert "приглашают в общее пространство «Наша пара»" in text
    assert "задач, списков, фильмов, поездок и заметок" in text
    assert "https://t.me/couple_test_bot?start=join_ABCD-1234" in text
    assert "48 часов" in text


def test_invite_message_has_copyable_fallback_and_escapes_name() -> None:
    text = _invite_message("Мы <3", "ABCD-1234", None)

    assert "Мы &lt;3" in text
    assert "<pre>/join ABCD-1234</pre>" in text


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


async def test_challenge_creator_can_edit_dates_without_losing_entries() -> None:
    async with SessionLocal() as session:
        couple_service = CoupleService(session)
        suffix = uuid4().int % 1_000_000_000
        user = await couple_service.get_or_create_user(
            telegram_id=940_000_000_000 + suffix,
            first_name="Owner",
        )
        couple, _ = await couple_service.create_couple(user, name=f"Dates {suffix}")
        service = ChallengeService(session)
        start = date.today()
        challenge = await service.create_challenge(
            couple.id,
            user.id,
            "Exercise",
            "PERSONAL",
            "SIMPLE",
            start,
            start + timedelta(days=2),
        )

        await service.set_date(
            couple.id,
            user.id,
            challenge.id,
            "end",
            start + timedelta(days=4),
        )
        await service.record_entry(
            couple.id,
            user.id,
            challenge.id,
            start,
            "SUCCESS",
        )
        with pytest.raises(ValidationError, match="сохранённые отметки"):
            await service.set_date(
                couple.id,
                user.id,
                challenge.id,
                "start",
                start + timedelta(days=1),
            )
        updated = await service.get_challenge(couple.id, user.id, challenge.id)

    assert updated.start_date == start
    assert updated.end_date == start + timedelta(days=4)


async def test_couple_savings_challenge_partner_sets_own_amount_later() -> None:
    async with SessionLocal() as session:
        couple_service = CoupleService(session)
        suffix = uuid4().int % 1_000_000_000
        owner = await couple_service.get_or_create_user(
            telegram_id=920_000_000_000 + suffix,
            first_name="Owner",
        )
        partner = await couple_service.get_or_create_user(
            telegram_id=930_000_000_000 + suffix,
            first_name="Partner",
        )
        couple, _ = await couple_service.create_couple(owner, name=f"Pair {suffix}")
        await couple_service.join_couple(partner, couple)

        service = ChallengeService(session)
        start = date.today()
        challenge = await service.create_challenge(
            couple.id,
            owner.id,
            "Не покупать кофе",
            "COUPLE",
            "SAVINGS",
            start,
            start + timedelta(days=2),
            Decimal("300"),
        )

        owner_view = await service.get_challenge(couple.id, owner.id, challenge.id)
        partner_view = await service.get_challenge(couple.id, partner.id, challenge.id)
        partner_participant = next(
            participant
            for participant in partner_view.participants
            if participant.user_id == partner.id
        )
        stats = ChallengeService.calculate_stats(partner_view, start)

        assert {participant.user_id for participant in owner_view.participants} == {
            owner.id,
            partner.id,
        }
        assert partner_participant.daily_amount is None
        assert stats.expected_amount_to_date == Decimal("300.00")

        await service.set_daily_amount(couple.id, partner.id, challenge.id, Decimal("150"))
        updated = await service.get_challenge(couple.id, partner.id, challenge.id)
        updated_stats = ChallengeService.calculate_stats(updated, start)

    assert updated_stats.expected_amount_to_date == Decimal("450.00")
