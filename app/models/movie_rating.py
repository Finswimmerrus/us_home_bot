from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MovieRating(Base):
    __tablename__ = "movie_ratings"
    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_movie_rating_range"),
        UniqueConstraint("movie_id", "user_id", name="uq_movie_rating"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    movie_id: Mapped[int] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    couple_id: Mapped[int] = mapped_column(
        ForeignKey("couples.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    movie: Mapped["Movie"] = relationship(back_populates="ratings", lazy="selectin")
    user: Mapped["User"] = relationship(foreign_keys=[user_id], lazy="selectin")

    def __repr__(self) -> str:
        return f"<MovieRating movie_id={self.movie_id} user_id={self.user_id} rating={self.rating}>"
