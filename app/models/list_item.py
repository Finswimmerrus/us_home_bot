from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ListItem(Base):
    __tablename__ = "list_items"
    __table_args__ = (
        CheckConstraint("title <> ''", name="ck_list_item_title_nonempty"),
        ForeignKeyConstraint(
            ["list_id", "couple_id"],
            ["lists.id", "lists.couple_id"],
            name="fk_list_item_list_couple",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    list_id: Mapped[int] = mapped_column(
        nullable=False,
        index=True,
    )
    couple_id: Mapped[int] = mapped_column(
        ForeignKey("couples.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=False
    )
    completed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
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

    list: Mapped["List"] = relationship(back_populates="items", lazy="selectin")
    created_by_user: Mapped["User"] = relationship(foreign_keys=[created_by], lazy="selectin")
    completed_by_user: Mapped["User | None"] = relationship(
        foreign_keys=[completed_by], lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<ListItem id={self.id} title={self.title} completed={self.completed_at is not None}>"
