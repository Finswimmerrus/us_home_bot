from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFound, ValidationError
from app.models.movie import Movie
from app.models.movie_rating import MovieRating

VALID_MOVIE_STATUSES = ["WANT_TO_WATCH", "WATCHING", "WATCHED"]


class MovieRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, movie_id: int) -> Movie | None:
        stmt = select(Movie).where(Movie.id == movie_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_couple(
        self, couple_id: int, movie_id: int
    ) -> Movie | None:
        stmt = select(Movie).where(
            Movie.id == movie_id, Movie.couple_id == couple_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_for_couple(
        self,
        couple_id: int,
        status: str | None = None,
        added_by: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Movie]:
        stmt = select(Movie).where(Movie.couple_id == couple_id)
        if status:
            stmt = stmt.where(Movie.status == status)
        if added_by is not None:
            stmt = stmt.where(Movie.added_by == added_by)
        stmt = stmt.order_by(Movie.created_at.desc())
        if limit:
            stmt = stmt.limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_status(self, couple_id: int, status: str) -> list[Movie]:
        stmt = (
            select(Movie)
            .where(Movie.couple_id == couple_id, Movie.status == status)
            .order_by(Movie.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        couple_id: int,
        title: str,
        description: str | None = None,
        status: str = "WANT_TO_WATCH",
        added_by: int | None = None,
    ) -> Movie:
        if status not in VALID_MOVIE_STATUSES:
            raise ValidationError(f"Invalid movie status: {status}", field="status")
        if added_by is None:
            raise ValidationError("added_by is required", field="added_by")
        movie = Movie(
            couple_id=couple_id,
            title=title,
            description=description,
            status=status,
            added_by=added_by,
        )
        self._session.add(movie)
        await self._session.flush()
        await self._session.refresh(movie)
        return movie

    async def update(self, movie: Movie) -> Movie:
        self._session.add(movie)
        await self._session.flush()
        await self._session.refresh(movie)
        return movie

    async def delete(self, movie: Movie) -> None:
        await self._session.delete(movie)
        await self._session.flush()

    async def change_status(self, movie: Movie, new_status: str) -> Movie:
        if new_status not in VALID_MOVIE_STATUSES:
            raise ValidationError(f"Invalid movie status: {new_status}", field="status")
        movie.status = new_status
        if new_status == "WATCHED" and not movie.watched_at:
            movie.watched_at = datetime.now(UTC)
        elif new_status != "WATCHED":
            movie.watched_at = None
        return await self.update(movie)


class MovieRatingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_rating(
        self, movie_id: int, user_id: int
    ) -> MovieRating | None:
        stmt = select(MovieRating).where(
            MovieRating.movie_id == movie_id,
            MovieRating.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def set_rating(
        self, movie_id: int, user_id: int, rating: int
    ) -> MovieRating:
        if not 1 <= rating <= 5:
            raise ValidationError("Rating must be between 1 and 5", field="rating")
        existing = await self.get_rating(movie_id, user_id)
        if existing is not None:
            existing.rating = rating
            self._session.add(existing)
            await self._session.flush()
            await self._session.refresh(existing)
            return existing

        movie = await self._session.get(Movie, movie_id)
        if movie is None:
            raise NotFound("Movie", movie_id)
        rating_obj = MovieRating(
            couple_id=movie.couple_id,
            movie_id=movie_id,
            user_id=user_id,
            rating=rating,
        )
        self._session.add(rating_obj)
        await self._session.flush()
        await self._session.refresh(rating_obj)
        return rating_obj

    async def get_average(self, movie_id: int) -> float | None:
        stmt = select(func.avg(MovieRating.rating)).where(
            MovieRating.movie_id == movie_id
        )
        result = await self._session.execute(stmt)
        avg_val = result.scalar()
        return float(avg_val) if avg_val is not None else None

    async def get_all_for_movie(self, movie_id: int) -> list[MovieRating]:
        stmt = select(MovieRating).where(MovieRating.movie_id == movie_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_user_ratings_for_couple(
        self, couple_id: int, user_id: int
    ) -> list[MovieRating]:
        stmt = (
            select(MovieRating)
            .join(Movie, Movie.id == MovieRating.movie_id)
            .where(Movie.couple_id == couple_id, MovieRating.user_id == user_id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
