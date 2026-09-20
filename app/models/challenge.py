from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.couple import Couple
    from app.models.user import User


class Challenge(Base):
    __tablename__ = "challenges"
    __table_args__ = (
        CheckConstraint("title <> ''", name="ck_challenge_title_nonempty"),
        CheckConstraint(
            "scope IN ('PERSONAL', 'COUPLE')",
            name="ck_challenge_scope",
        ),
        CheckConstraint(
            "challenge_type IN ('SIMPLE', 'SAVINGS')",
            name="ck_challenge_type",
        ),
        CheckConstraint("end_date >= start_date", name="ck_challenge_period"),
        CheckConstraint(
            "(challenge_type = 'SAVINGS' AND (daily_amount IS NULL OR daily_amount >= 0)) "
            "OR (challenge_type = 'SIMPLE' AND daily_amount IS NULL)",
            name="ck_challenge_daily_amount",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    couple_id: Mapped[int] = mapped_column(
        ForeignKey("couples.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    challenge_type: Mapped[str] = mapped_column(String(32), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    daily_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default="RUB", default="RUB"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    couple: Mapped[Couple] = relationship(lazy="selectin")
    creator: Mapped[User] = relationship(foreign_keys=[created_by], lazy="selectin")
    participants: Mapped[list[ChallengeParticipant]] = relationship(
        back_populates="challenge", lazy="selectin", cascade="all, delete-orphan"
    )
    entries: Mapped[list[ChallengeEntry]] = relationship(
        back_populates="challenge", lazy="selectin", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Challenge id={self.id} title={self.title} scope={self.scope}>"


class ChallengeParticipant(Base):
    __tablename__ = "challenge_participants"
    __table_args__ = (
        UniqueConstraint("challenge_id", "user_id", name="uq_challenge_participant"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    challenge_id: Mapped[int] = mapped_column(
        ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    daily_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    challenge: Mapped[Challenge] = relationship(back_populates="participants", lazy="selectin")
    user: Mapped[User] = relationship(lazy="selectin")

    def __repr__(self) -> str:
        return f"<ChallengeParticipant challenge_id={self.challenge_id} user_id={self.user_id}>"


class ChallengeEntry(Base):
    __tablename__ = "challenge_entries"
    __table_args__ = (
        UniqueConstraint(
            "challenge_id",
            "user_id",
            "entry_date",
            name="uq_challenge_entry_day",
        ),
        CheckConstraint(
            "status IN ('SUCCESS', 'MISSED')",
            name="ck_challenge_entry_status",
        ),
        CheckConstraint("spent_amount IS NULL OR spent_amount >= 0", name="ck_challenge_spent"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    challenge_id: Mapped[int] = mapped_column(
        ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    spent_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    challenge: Mapped[Challenge] = relationship(back_populates="entries", lazy="selectin")
    user: Mapped[User] = relationship(lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<ChallengeEntry challenge_id={self.challenge_id} "
            f"user_id={self.user_id} date={self.entry_date} status={self.status}>"
        )
