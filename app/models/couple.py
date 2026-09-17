from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Couple(Base):
    __tablename__ = "couples"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    invite_code: Mapped[str | None] = mapped_column(
        String(32), unique=True, nullable=True, index=True
    )
    invite_expires_at: Mapped[datetime | None] = mapped_column(
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

    members: Mapped[list["CoupleMember"]] = relationship(
        back_populates="couple", lazy="selectin", cascade="all, delete-orphan"
    )

    @property
    def member_count(self) -> int:
        return len(self.members)

    def __repr__(self) -> str:
        return f"<Couple id={self.id} name={self.name}>"
