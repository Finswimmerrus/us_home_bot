from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CoupleMember(Base):
    __tablename__ = "couple_members"
    __table_args__ = (
        UniqueConstraint("couple_id", "user_id", name="uq_couple_member"),
        UniqueConstraint("user_id", name="uq_couple_member_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    couple_id: Mapped[int] = mapped_column(
        ForeignKey("couples.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    couple: Mapped["Couple"] = relationship(back_populates="members", lazy="selectin")
    user: Mapped["User"] = relationship(back_populates="memberships", lazy="selectin")

    def __repr__(self) -> str:
        return f"<CoupleMember couple_id={self.couple_id} user_id={self.user_id}>"
