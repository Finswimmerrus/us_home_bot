from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ValidationError
from app.models.trip import Trip, TripPlace


class TripRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, trip_id: int) -> Trip | None:
        stmt = select(Trip).where(Trip.id == trip_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_couple(
        self, couple_id: int, trip_id: int
    ) -> Trip | None:
        stmt = select(Trip).where(
            Trip.id == trip_id, Trip.couple_id == couple_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_for_couple(
        self,
        couple_id: int,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Trip]:
        stmt = select(Trip).where(Trip.couple_id == couple_id)
        stmt = stmt.order_by(
            Trip.start_date.desc().nullslast(), Trip.created_at.desc()
        )
        if limit:
            stmt = stmt.limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        couple_id: int,
        created_by: int,
        name: str,
        description: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> Trip:
        if not name or not name.strip():
            raise ValidationError("Trip name cannot be empty", field="name")
        trip = Trip(
            couple_id=couple_id,
            created_by=created_by,
            name=name.strip(),
            description=description,
            start_date=start_date,
            end_date=end_date,
        )
        self._session.add(trip)
        await self._session.flush()
        await self._session.refresh(trip)
        return trip

    async def update(self, trip: Trip) -> Trip:
        self._session.add(trip)
        await self._session.flush()
        await self._session.refresh(trip)
        return trip

    async def delete(self, trip: Trip) -> None:
        await self._session.delete(trip)
        await self._session.flush()


class PlaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, place_id: int) -> TripPlace | None:
        stmt = select(TripPlace).where(TripPlace.id == place_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_trip(
        self, trip_id: int, place_id: int
    ) -> TripPlace | None:
        stmt = select(TripPlace).where(
            TripPlace.id == place_id, TripPlace.trip_id == trip_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_for_trip(self, trip_id: int) -> list[TripPlace]:
        stmt = (
            select(TripPlace)
            .where(TripPlace.trip_id == trip_id)
            .order_by(TripPlace.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_for_couple(self, couple_id: int) -> list[TripPlace]:
        stmt = (
            select(TripPlace)
            .join(Trip, Trip.id == TripPlace.trip_id)
            .where(Trip.couple_id == couple_id)
            .order_by(TripPlace.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        trip_id: int,
        couple_id: int,
        name: str,
        description: str | None = None,
        address: str | None = None,
        url: str | None = None,
        visit_date: date | None = None,
    ) -> TripPlace:
        if not name or not name.strip():
            raise ValidationError("Place name cannot be empty", field="name")
        place = TripPlace(
            trip_id=trip_id,
            couple_id=couple_id,
            name=name.strip(),
            description=description,
            address=address,
            url=url,
            visit_date=visit_date,
        )
        self._session.add(place)
        await self._session.flush()
        await self._session.refresh(place)
        return place

    async def update(self, place: TripPlace) -> TripPlace:
        self._session.add(place)
        await self._session.flush()
        await self._session.refresh(place)
        return place

    async def delete(self, place: TripPlace) -> None:
        await self._session.delete(place)
        await self._session.flush()
