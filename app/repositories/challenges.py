from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.challenge import Challenge, ChallengeEntry, ChallengeParticipant


class ChallengeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, challenge_id: int) -> Challenge | None:
        stmt = (
            select(Challenge)
            .options(
                selectinload(Challenge.participants).selectinload(ChallengeParticipant.user),
                selectinload(Challenge.entries),
            )
            .where(Challenge.id == challenge_id)
            .execution_options(populate_existing=True)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_user(self, couple_id: int, user_id: int) -> list[Challenge]:
        stmt = (
            select(Challenge)
            .join(ChallengeParticipant)
            .options(
                selectinload(Challenge.participants).selectinload(ChallengeParticipant.user),
                selectinload(Challenge.entries),
            )
            .where(
                Challenge.couple_id == couple_id,
                ChallengeParticipant.user_id == user_id,
            )
            .order_by(Challenge.end_date.asc(), Challenge.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().unique().all())

    async def create(
        self,
        couple_id: int,
        created_by: int,
        title: str,
        scope: str,
        challenge_type: str,
        start_date: date,
        end_date: date,
        participant_ids: list[int],
        participant_daily_amounts: dict[int, Decimal] | None = None,
        daily_amount: Decimal | None = None,
        currency: str = "RUB",
    ) -> Challenge:
        challenge = Challenge(
            couple_id=couple_id,
            created_by=created_by,
            title=title,
            scope=scope,
            challenge_type=challenge_type,
            start_date=start_date,
            end_date=end_date,
            daily_amount=daily_amount,
            currency=currency,
        )
        self._session.add(challenge)
        await self._session.flush()
        amounts = participant_daily_amounts or {}
        for participant_id in participant_ids:
            self._session.add(
                ChallengeParticipant(
                    challenge_id=challenge.id,
                    user_id=participant_id,
                    daily_amount=amounts.get(participant_id),
                )
            )
        await self._session.flush()
        await self._session.refresh(challenge)
        return challenge

    async def get_entry(
        self,
        challenge_id: int,
        user_id: int,
        entry_date: date,
    ) -> ChallengeEntry | None:
        stmt = select(ChallengeEntry).where(
            ChallengeEntry.challenge_id == challenge_id,
            ChallengeEntry.user_id == user_id,
            ChallengeEntry.entry_date == entry_date,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_entry(
        self,
        challenge_id: int,
        user_id: int,
        entry_date: date,
        status: str,
        spent_amount: Decimal | None,
    ) -> ChallengeEntry:
        entry = await self.get_entry(challenge_id, user_id, entry_date)
        if entry is None:
            entry = ChallengeEntry(
                challenge_id=challenge_id,
                user_id=user_id,
                entry_date=entry_date,
                status=status,
                spent_amount=spent_amount,
            )
            self._session.add(entry)
        else:
            entry.status = status
            entry.spent_amount = spent_amount
        await self._session.flush()
        await self._session.refresh(entry)
        return entry

    async def set_participant_daily_amount(
        self,
        challenge_id: int,
        user_id: int,
        daily_amount: Decimal,
    ) -> ChallengeParticipant | None:
        stmt = select(ChallengeParticipant).where(
            ChallengeParticipant.challenge_id == challenge_id,
            ChallengeParticipant.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        participant = result.scalar_one_or_none()
        if participant is None:
            return None
        participant.daily_amount = daily_amount
        await self._session.flush()
        await self._session.refresh(participant)
        return participant

    async def set_dates(
        self,
        challenge: Challenge,
        start_date: date,
        end_date: date,
    ) -> Challenge:
        challenge.start_date = start_date
        challenge.end_date = end_date
        await self._session.flush()
        await self._session.refresh(challenge)
        return challenge
