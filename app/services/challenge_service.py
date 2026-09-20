from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import Forbidden, NotFound, ValidationError
from app.models.challenge import Challenge, ChallengeEntry, ChallengeParticipant
from app.repositories.challenges import ChallengeRepository
from app.repositories.users import CoupleMemberRepository

VALID_CHALLENGE_SCOPES = ["PERSONAL", "COUPLE"]
VALID_CHALLENGE_TYPES = ["SIMPLE", "SAVINGS"]
VALID_CHALLENGE_STATUSES = ["SUCCESS", "MISSED"]
RUB = "RUB"


@dataclass(frozen=True)
class ChallengeStats:
    participant_count: int
    elapsed_days: int
    actual_spending: Decimal
    expected_amount_to_date: Decimal
    calculated_savings: Decimal


class ChallengeService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._challenge_repo = ChallengeRepository(session)
        self._member_repo = CoupleMemberRepository(session)

    async def create_challenge(
        self,
        couple_id: int,
        created_by: int,
        title: str,
        scope: str,
        challenge_type: str,
        start_date: date,
        end_date: date,
        daily_amount: Decimal | None = None,
        participant_daily_amounts: dict[int, Decimal | str | int | None] | None = None,
        currency: str = RUB,
    ) -> Challenge:
        await self._member_repo.validate_membership(couple_id, created_by)
        title = title.strip()
        if not title:
            raise ValidationError("Введите название челленджа.", field="title")
        if scope not in VALID_CHALLENGE_SCOPES:
            raise ValidationError("Некорректный формат челленджа.", field="scope")
        if challenge_type not in VALID_CHALLENGE_TYPES:
            raise ValidationError("Некорректный тип челленджа.", field="challenge_type")
        if end_date < start_date:
            raise ValidationError("Дата окончания не может быть раньше даты начала.", field="end_date")

        member_ids = await self._member_repo.get_member_user_ids(couple_id)
        if scope == "PERSONAL":
            participant_ids = [created_by]
        else:
            if len(member_ids) < 2:
                raise ValidationError(
                    "Для общего челленджа сначала добавьте партнёра.",
                    field="scope",
                )
            participant_ids = member_ids

        amount = None
        participant_amounts: dict[int, Decimal] | None = None
        if challenge_type == "SAVINGS":
            raw_amounts = participant_daily_amounts or {}
            creator_amount = self.normalize_money(
                raw_amounts.get(created_by, daily_amount)
            )
            if creator_amount is None:
                raise ValidationError("Введите свою сумму на день.", field="daily_amount")
            participant_amounts = {created_by: creator_amount}
            amount = creator_amount
        elif daily_amount is not None:
            raise ValidationError("Сумма нужна только для челленджа с экономией.", field="daily_amount")

        return await self._challenge_repo.create(
            couple_id=couple_id,
            created_by=created_by,
            title=title,
            scope=scope,
            challenge_type=challenge_type,
            start_date=start_date,
            end_date=end_date,
            daily_amount=amount,
            participant_daily_amounts=participant_amounts,
            currency=currency,
            participant_ids=participant_ids,
        )

    async def list_challenges(self, couple_id: int, user_id: int) -> list[Challenge]:
        await self._member_repo.validate_membership(couple_id, user_id)
        return await self._challenge_repo.list_for_user(couple_id, user_id)

    async def get_challenge(self, couple_id: int, user_id: int, challenge_id: int) -> Challenge:
        await self._member_repo.validate_membership(couple_id, user_id)
        challenge = await self._challenge_repo.get_by_id(challenge_id)
        if challenge is None or challenge.couple_id != couple_id:
            raise NotFound("Challenge", challenge_id)
        if user_id not in {participant.user_id for participant in challenge.participants}:
            raise Forbidden("access challenge", {"challenge_id": challenge_id, "user_id": user_id})
        return challenge

    async def record_entry(
        self,
        couple_id: int,
        user_id: int,
        challenge_id: int,
        entry_date: date,
        status: str,
        spent_amount: Decimal | None = None,
        today: date | None = None,
    ) -> ChallengeEntry:
        today = today or date.today()
        challenge = await self.get_challenge(couple_id, user_id, challenge_id)
        if status not in VALID_CHALLENGE_STATUSES:
            raise ValidationError("Некорректный статус.", field="status")
        if entry_date < challenge.start_date or entry_date > challenge.end_date:
            raise ValidationError("Эта дата вне периода челленджа.", field="entry_date")
        if entry_date > today:
            raise ValidationError("Будущие даты отмечать нельзя.", field="entry_date")

        amount = self.normalize_money(spent_amount) if spent_amount is not None else None
        if challenge.challenge_type == "SIMPLE":
            amount = None
        elif status == "SUCCESS":
            amount = Decimal("0.00")
        elif amount is None:
            raise ValidationError("Введите фактические траты.", field="spent_amount")

        return await self._challenge_repo.upsert_entry(
            challenge_id=challenge.id,
            user_id=user_id,
            entry_date=entry_date,
            status=status,
            spent_amount=amount,
        )

    async def set_daily_amount(
        self,
        couple_id: int,
        user_id: int,
        challenge_id: int,
        daily_amount: Decimal | str | int | None,
    ) -> ChallengeParticipant:
        challenge = await self.get_challenge(couple_id, user_id, challenge_id)
        if challenge.challenge_type != "SAVINGS":
            raise ValidationError("Сумма на день есть только в челлендже с экономией.", field="daily_amount")
        amount = self.normalize_money(daily_amount)
        if amount is None:
            raise ValidationError("Введите сумму на день.", field="daily_amount")
        participant = await self._challenge_repo.set_participant_daily_amount(
            challenge.id,
            user_id,
            amount,
        )
        if participant is None:
            raise Forbidden("update challenge amount", {"challenge_id": challenge_id, "user_id": user_id})
        return participant

    @staticmethod
    def calculate_stats(challenge: Challenge, today: date | None = None) -> ChallengeStats:
        today = today or date.today()
        participant_ids = {participant.user_id for participant in challenge.participants}
        elapsed_until = min(today, challenge.end_date)
        elapsed_days = 0
        if elapsed_until >= challenge.start_date:
            elapsed_days = (elapsed_until - challenge.start_date).days + 1
        actual_spending = sum(
            (entry.spent_amount or Decimal("0.00"))
            for entry in challenge.entries
            if entry.user_id in participant_ids and entry.entry_date <= elapsed_until
        )
        expected_per_day = sum(
            participant.daily_amount or Decimal("0.00")
            for participant in challenge.participants
            if participant.user_id in participant_ids
        )
        expected = expected_per_day * Decimal(elapsed_days)
        return ChallengeStats(
            participant_count=len(participant_ids),
            elapsed_days=elapsed_days,
            actual_spending=actual_spending,
            expected_amount_to_date=expected,
            calculated_savings=expected - actual_spending,
        )

    @staticmethod
    def normalize_money(value: Decimal | str | int | None) -> Decimal | None:
        if value is None:
            return None
        try:
            amount = Decimal(str(value).replace(",", ".")).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError) as exc:
            raise ValidationError("Введите сумму числом.", field="amount") from exc
        if amount < 0:
            raise ValidationError("Сумма не может быть отрицательной.", field="amount")
        return amount
