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
    from app.models.movie_rating import MovieRating
    from app.models.user import User


class Movie(Base):
    __tablename__ = "movies"
    __table_args__ = (
        CheckConstraint(
            "type IN ('MOVIE', 'SERIES')",
            name="ck_movie_type",
        ),
        CheckConstraint(
            "status IN ('WANT_TO_WATCH', 'WATCHING', 'WATCHED')",
            name="ck_movie_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    couple_id: Mapped[int] = mapped_column(
        ForeignKey("couples.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="MOVIE", default="MOVIE"
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="WANT_TO_WATCH", default="WANT_TO_WATCH"
    )
    added_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=False
    )
    watched_at: Mapped[datetime | None] = mapped_column(
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

    added_by_user: Mapped[User] = relationship(foreign_keys=[added_by], lazy="selectin")
    ratings: Mapped[list[MovieRating]] = relationship(
        back_populates="movie", lazy="selectin", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Movie id={self.id} title={self.title} status={self.status}>"
