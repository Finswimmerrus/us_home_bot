from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.trip import Trip
    from app.models.user import User


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "assignment_type IN ('CREATOR', 'PARTNER', 'BOTH')",
            name="ck_task_assignment_type",
        ),
        CheckConstraint(
            "status IN ('TODO', 'IN_PROGRESS', 'DONE', 'CANCELLED')",
            name="ck_task_status",
        ),
        CheckConstraint(
            "priority IN ('LOW', 'NORMAL', 'HIGH')",
            name="ck_task_priority",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    couple_id: Mapped[int] = mapped_column(
        ForeignKey("couples.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=False
    )
    assigned_to: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assignment_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="CREATOR", default="CREATOR"
    )
    completed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    trip_id: Mapped[int | None] = mapped_column(
        ForeignKey("trips.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="TODO", default="TODO"
    )
    priority: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="NORMAL", default="NORMAL"
    )
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    creator: Mapped[User] = relationship(foreign_keys=[created_by], lazy="selectin")
    assignee: Mapped[User | None] = relationship(
        foreign_keys=[assigned_to], lazy="selectin"
    )
    completer: Mapped[User | None] = relationship(
        foreign_keys=[completed_by], lazy="selectin"
    )
    trip: Mapped[Trip | None] = relationship(lazy="selectin")

    def __repr__(self) -> str:
        return f"<Task id={self.id} title={self.title} status={self.status}>"
