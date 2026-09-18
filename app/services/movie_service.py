from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFound, ValidationError
from app.models.movie import Movie
from app.models.movie_rating import MovieRating
from app.repositories.movies import MovieRatingRepository, MovieRepository
from app.repositories.users import (
    CoupleMemberRepository,
    UserRepository,
)

logger = logging.getLogger(__name__)

VALID_MOVIE_STATUSES = ["WANT_TO_WATCH", "WATCHING", "WATCHED"]


class MovieService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._movie_repo = MovieRepository(session)
        self._rating_repo = MovieRatingRepository(session)
        self._user_repo = UserRepository(session)
        self._member_repo = CoupleMemberRepository(session)

    async def _validate_access(
        self, couple_id: int, user_id: int
    ) -> None:
        await self._member_repo.validate_membership(couple_id, user_id)

    async def add_movie(
        self,
        couple_id: int,
        user_id: int,
        title: str,
        description: str | None = None,
        status: str = "WANT_TO_WATCH",
    ) -> Movie:
        await self._validate_access(couple_id, user_id)
        if not title or not title.strip():
            raise ValidationError(
                "Movie title cannot be empty", field="title"
            )
        if status not in VALID_MOVIE_STATUSES:
            raise ValidationError(
                f"Invalid movie status: {status}", field="status"
            )
        movie = await self._movie_repo.create(
            couple_id=couple_id,
            title=title.strip(),
            description=description,
            status=status,
            added_by=user_id,
        )
        logger.info(
            "Added movie id=%s to couple id=%s by user id=%s",
            movie.id, couple_id, user_id,
        )
        return movie

    async def get_movie(
        self, couple_id: int, user_id: int, movie_id: int
    ) -> Movie:
        await self._validate_access(couple_id, user_id)
        movie = await self._movie_repo.get_for_couple(couple_id, movie_id)
        if movie is None:
            raise NotFound("Movie", movie_id)
        return movie

    async def get_movies_by_status(
        self, couple_id: int, user_id: int, status: str
    ) -> list[Movie]:
        await self._validate_access(couple_id, user_id)
        if status not in VALID_MOVIE_STATUSES:
            raise ValidationError(
                f"Invalid movie status: {status}", field="status"
            )
        return await self._movie_repo.get_by_status(couple_id, status)

    async def get_all_movies(
        self,
        couple_id: int,
        user_id: int,
        status: str | None = None,
        added_by: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Movie]:
        await self._validate_access(couple_id, user_id)
        if added_by is not None:
            await self._member_repo.validate_membership(
                couple_id, added_by
            )
        return await self._movie_repo.get_all_for_couple(
            couple_id,
            status=status,
            added_by=added_by,
            limit=limit,
            offset=offset,
        )

    async def update_movie(
        self,
        couple_id: int,
        user_id: int,
        movie_id: int,
        title: str | None = None,
        description: str | None = None,
    ) -> Movie:
        await self._validate_access(couple_id, user_id)
        movie = await self._movie_repo.get_for_couple(couple_id, movie_id)
        if movie is None:
            raise NotFound("Movie", movie_id)
        if title is not None:
            if not title.strip():
                raise ValidationError(
                    "Movie title cannot be empty", field="title"
                )
            movie.title = title.strip()
        if description is not None:
            movie.description = description
        return await self._movie_repo.update(movie)

    async def change_status(
        self,
        couple_id: int,
        user_id: int,
        movie_id: int,
        new_status: str,
    ) -> Movie:
        await self._validate_access(couple_id, user_id)
        movie = await self._movie_repo.get_for_couple(couple_id, movie_id)
        if movie is None:
            raise NotFound("Movie", movie_id)
        return await self._movie_repo.change_status(movie, new_status)

    async def delete_movie(
        self, couple_id: int, user_id: int, movie_id: int
    ) -> None:
        await self._validate_access(couple_id, user_id)
        movie = await self._movie_repo.get_for_couple(couple_id, movie_id)
        if movie is None:
            raise NotFound("Movie", movie_id)
        await self._movie_repo.delete(movie)
        logger.info(
            "Deleted movie id=%s from couple id=%s by user id=%s",
            movie_id, couple_id, user_id,
        )

    async def rate_movie(
        self,
        couple_id: int,
        user_id: int,
        movie_id: int,
        rating: int,
    ) -> MovieRating:
        await self._validate_access(couple_id, user_id)
        movie = await self._movie_repo.get_for_couple(couple_id, movie_id)
        if movie is None:
            raise NotFound("Movie", movie_id)
        if not 1 <= rating <= 5:
            raise ValidationError(
                "Rating must be between 1 and 5", field="rating"
            )
        result = await self._rating_repo.set_rating(
            movie_id, user_id, rating
        )
        logger.info(
            "User id=%s rated movie id=%s: %d",
            user_id, movie_id, rating,
        )
        return result

    async def get_ratings_for_movie(
        self, couple_id: int, user_id: int, movie_id: int
    ) -> list[MovieRating]:
        await self._validate_access(couple_id, user_id)
        movie = await self._movie_repo.get_for_couple(couple_id, movie_id)
        if movie is None:
            raise NotFound("Movie", movie_id)
        return await self._rating_repo.get_all_for_movie(movie_id)

    async def get_average_rating(
        self, couple_id: int, user_id: int, movie_id: int
    ) -> float | None:
        await self._validate_access(couple_id, user_id)
        movie = await self._movie_repo.get_for_couple(couple_id, movie_id)
        if movie is None:
            raise NotFound("Movie", movie_id)
        return await self._rating_repo.get_average(movie_id)

    async def get_user_ratings(
        self, couple_id: int, user_id: int
    ) -> list[MovieRating]:
        await self._validate_access(couple_id, user_id)
        return await self._rating_repo.get_user_ratings_for_couple(
            couple_id, user_id
        )

    async def get_couple_rating_stats(
        self, couple_id: int, user_id: int
    ) -> dict:
        await self._validate_access(couple_id, user_id)
        movies = await self._movie_repo.get_all_for_couple(couple_id)
        watched = [m for m in movies if m.status == "WATCHED"]
        total_ratings = 0
        sum_ratings = 0.0
        for movie in watched:
            avg = await self._rating_repo.get_average(movie.id)
            if avg is not None:
                total_ratings += 1
                sum_ratings += avg
        return {
            "total_movies": len(movies),
            "watched_movies": len(watched),
            "rated_movies": total_ratings,
            "average_rating": (
                sum_ratings / total_ratings if total_ratings > 0 else None
            ),
        }
