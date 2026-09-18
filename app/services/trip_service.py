import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFound, ValidationError
from app.models.trip import Trip, TripPlace
from app.repositories.trips import PlaceRepository, TripRepository
from app.repositories.users import CoupleMemberRepository

logger = logging.getLogger(__name__)


class TripService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._trip_repo = TripRepository(session)
        self._place_repo = PlaceRepository(session)
        self._member_repo = CoupleMemberRepository(session)

    async def _validate_access(self, couple_id: int, user_id: int) -> None:
        await self._member_repo.validate_membership(couple_id, user_id)

    async def _validate_trip_access(
        self, couple_id: int, user_id: int, trip_id: int
    ) -> Trip:
        await self._validate_access(couple_id, user_id)
        trip = await self._trip_repo.get_for_couple(couple_id, trip_id)
        if trip is None:
            raise NotFound("Trip", trip_id)
        return trip

    async def create_trip(
        self,
        couple_id: int,
        user_id: int,
        title: str,
        description: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> Trip:
        await self._validate_access(couple_id, user_id)
        if not title or not title.strip():
            raise ValidationError("Trip title cannot be empty", field="title")
        if start_date and end_date and end_date < start_date:
            raise ValidationError("End date cannot be before start date", field="end_date")

        trip = await self._trip_repo.create(
            couple_id=couple_id,
            created_by=user_id,
            name=title.strip(),
            description=description,
            start_date=start_date,
            end_date=end_date,
        )
        logger.info("Created trip id=%s in couple id=%s by user id=%s", trip.id, couple_id, user_id)
        return trip

    async def get_trip(self, couple_id: int, user_id: int, trip_id: int) -> Trip:
        return await self._validate_trip_access(couple_id, user_id, trip_id)

    async def get_all_trips(
        self,
        couple_id: int,
        user_id: int,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Trip]:
        await self._validate_access(couple_id, user_id)
        return await self._trip_repo.get_all_for_couple(
            couple_id, limit=limit, offset=offset
        )

    async def update_trip(
        self,
        couple_id: int,
        user_id: int,
        trip_id: int,
        title: str | None = None,
        description: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> Trip:
        trip = await self._validate_trip_access(couple_id, user_id, trip_id)

        if title is not None:
            if not title.strip():
                raise ValidationError("Trip title cannot be empty", field="title")
            trip.name = title.strip()
        if description is not None:
            trip.description = description
        if start_date is not None:
            trip.start_date = start_date
        if end_date is not None:
            trip.end_date = end_date

        if trip.start_date and trip.end_date and trip.end_date < trip.start_date:
            raise ValidationError("End date cannot be before start date", field="end_date")

        return await self._trip_repo.update(trip)

    async def delete_trip(self, couple_id: int, user_id: int, trip_id: int) -> None:
        trip = await self._validate_trip_access(couple_id, user_id, trip_id)
        await self._trip_repo.delete(trip)
        logger.info("Deleted trip id=%s in couple id=%s by user id=%s", trip_id, couple_id, user_id)


class PlaceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._trip_repo = TripRepository(session)
        self._place_repo = PlaceRepository(session)
        self._member_repo = CoupleMemberRepository(session)

    async def _validate_access(self, couple_id: int, user_id: int) -> None:
        await self._member_repo.validate_membership(couple_id, user_id)

    async def _validate_trip_and_place(
        self, couple_id: int, user_id: int, trip_id: int, place_id: int
    ) -> tuple[Trip, TripPlace]:
        await self._validate_access(couple_id, user_id)
        trip = await self._trip_repo.get_for_couple(couple_id, trip_id)
        if trip is None:
            raise NotFound("Trip", trip_id)
        place = await self._place_repo.get_for_trip(trip_id, place_id)
        if place is None:
            raise NotFound("Place", place_id)
        return trip, place

    async def add_place(
        self,
        couple_id: int,
        user_id: int,
        trip_id: int,
        title: str,
        description: str | None = None,
        address: str | None = None,
        url: str | None = None,
        visit_date: date | None = None,
    ) -> TripPlace:
        await self._validate_access(couple_id, user_id)
        trip = await self._trip_repo.get_for_couple(couple_id, trip_id)
        if trip is None:
            raise NotFound("Trip", trip_id)
        if not title or not title.strip():
            raise ValidationError("Place title cannot be empty", field="title")

        place = await self._place_repo.create(
            trip_id=trip_id,
            couple_id=couple_id,
            name=title.strip(),
            description=description,
            address=address,
            url=url,
            visit_date=visit_date,
        )
        logger.info("Added place id=%s to trip id=%s by user id=%s", place.id, trip_id, user_id)
        return place

    async def get_places_for_trip(
        self, couple_id: int, user_id: int, trip_id: int
    ) -> list[TripPlace]:
        await self._validate_access(couple_id, user_id)
        trip = await self._trip_repo.get_for_couple(couple_id, trip_id)
        if trip is None:
            raise NotFound("Trip", trip_id)
        return await self._place_repo.get_all_for_trip(trip_id)

    async def get_place(
        self, couple_id: int, user_id: int, trip_id: int, place_id: int
    ) -> TripPlace:
        _, place = await self._validate_trip_and_place(
            couple_id, user_id, trip_id, place_id
        )
        return place

    async def update_place(
        self,
        couple_id: int,
        user_id: int,
        trip_id: int,
        place_id: int,
        title: str | None = None,
        description: str | None = None,
        address: str | None = None,
        url: str | None = None,
        visit_date: date | None = None,
    ) -> TripPlace:
        _, place = await self._validate_trip_and_place(
            couple_id, user_id, trip_id, place_id
        )

        if title is not None:
            if not title.strip():
                raise ValidationError("Place title cannot be empty", field="title")
            place.name = title.strip()
        if description is not None:
            place.description = description
        if address is not None:
            place.address = address
        if url is not None:
            place.url = url
        if visit_date is not None:
            place.visit_date = visit_date

        return await self._place_repo.update(place)

    async def delete_place(
        self, couple_id: int, user_id: int, trip_id: int, place_id: int
    ) -> None:
        _, place = await self._validate_trip_and_place(
            couple_id, user_id, trip_id, place_id
        )
        await self._place_repo.delete(place)
        logger.info("Deleted place id=%s from trip id=%s by user id=%s", place_id, trip_id, user_id)

    async def get_all_places_for_couple(
        self, couple_id: int, user_id: int
    ) -> list[TripPlace]:
        await self._validate_access(couple_id, user_id)
        return await self._place_repo.get_all_for_couple(couple_id)
