from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note import Note
from app.exceptions import NotFound, ValidationError


class NoteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, note_id: int) -> Note | None:
        stmt = select(Note).where(Note.id == note_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_couple(
        self, couple_id: int, note_id: int
    ) -> Note | None:
        stmt = select(Note).where(
            Note.id == note_id, Note.couple_id == couple_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_for_couple(
        self,
        couple_id: int,
        created_by: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Note]:
        stmt = select(Note).where(Note.couple_id == couple_id)
        if created_by is not None:
            stmt = stmt.where(Note.created_by == created_by)
        stmt = stmt.order_by(Note.updated_at.desc().nullslast(), Note.created_at.desc())
        if limit:
            stmt = stmt.limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def search(
        self,
        couple_id: int,
        query: str,
        created_by: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Note]:
        if not query or not query.strip():
            return []
        search_term = f"%{query.strip()}%"
        stmt = select(Note).where(
            Note.couple_id == couple_id,
            or_(
                Note.title.ilike(search_term),
                Note.content.ilike(search_term),
            ),
        )
        if created_by is not None:
            stmt = stmt.where(Note.created_by == created_by)
        stmt = stmt.order_by(
            Note.updated_at.desc().nullslast(), Note.created_at.desc()
        )
        stmt = stmt.limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        couple_id: int,
        created_by: int,
        title: str,
        content: str | None = None,
    ) -> Note:
        if not title or not title.strip():
            raise ValidationError("Note title cannot be empty", field="title")
        note = Note(
            couple_id=couple_id,
            created_by=created_by,
            title=title.strip(),
            content=content,
        )
        self._session.add(note)
        await self._session.flush()
        await self._session.refresh(note)
        return note

    async def update(self, note: Note) -> Note:
        self._session.add(note)
        await self._session.flush()
        await self._session.refresh(note)
        return note

    async def delete(self, note: Note) -> None:
        await self._session.delete(note)
        await self._session.flush()