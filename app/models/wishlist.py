from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class WishlistItem(Base):
    __tablename__ = "wishlist_items"
    __table_args__ = (
        CheckConstraint("title <> ''", name="ck_wishlist_title_nonempty"),
        CheckConstraint(
            "status IN ('WANTED', 'PURCHASED', 'ARCHIVED')",
            name="ck_wishlist_status",
        ),
        CheckConstraint(
            "(url LIKE 'http://%' OR url LIKE 'https://%' OR url IS NULL)",
            name="ck_wishlist_url_scheme",
        ),
        CheckConstraint("priority >= 0", name="ck_wishlist_priority"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    couple_id: Mapped[int] = mapped_column(
        ForeignKey("couples.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    priority: Mapped[int] = mapped_column(
        nullable=False, server_default="0", default=0
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="WANTED", default="WANTED"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    couple: Mapped["Couple"] = relationship(lazy="selectin")
    owner: Mapped["User | None"] = relationship(foreign_keys=[owner_id], lazy="selectin")

    def __repr__(self) -> str:
        return f"<WishlistItem id={self.id} couple_id={self.couple_id} title={self.title}>"
