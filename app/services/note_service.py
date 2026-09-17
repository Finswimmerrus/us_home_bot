from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.users import CoupleMemberRepository
from app.repositories.notes import NoteRepository
from app.exceptions import NotFound, Forbidden, ValidationError

logger = logging.getLogger(__name__)


class NoteService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._note_repo = NoteRepository(session)
        self._member_repo = CoupleMemberRepository(session)

    async def _validate_access(
        self, couple_id: int, user_id: int
    ) -> None:
        await self._member_repo.validate_membership(couple_id, user_id)

    async def _validate_note_access(
        self, couple_id: int, user_id: int, note_id: int
    ):
        await self._validate_access(couple_id, user_id)
        note = await self._note_repo.get_for_couple(couple_id, note_id)
        if note is None:
            raise NotFound("Note", note_id)
        return note

    async def create_note(
        self,
        couple_id: int,
        user_id: int,
        title: str,
        content: str | None = None,
    ):
        await self._validate_access(couple_id, user_id)
        if not title or not title.strip():
            raise ValidationError(
                "Note title cannot be empty", field="title"
            )
        note = await self._note_repo.create(
            couple_id=couple_id,
            created_by=user_id,
            title=title.strip(),
            content=content,
        )
        logger.info(
            "Created note id=%s in couple id=%s by user id=%s",
            note.id, couple_id, user_id,
        )
        return note

    async def get_note(
        self, couple_id: int, user_id: int, note_id: int
    ):
        return await self._validate_note_access(couple_id, user_id, note_id)

    async def get_all_notes(
        self,
        couple_id: int,
        user_id: int,
        created_by: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list:
        await self._validate_access(couple_id, user_id)
        if created_by is not None:
            await self._member_repo.validate_membership(
                couple_id, created_by
            )
        return await self._note_repo.get_all_for_couple(
            couple_id,
            created_by=created_by,
            limit=limit,
            offset=offset,
        )

    async def search_notes(
        self,
        couple_id: int,
        user_id: int,
        query: str,
        created_by: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list:
        await self._validate_access(couple_id, user_id)
        if created_by is not None:
            await self._member_repo.validate_membership(
                couple_id, created_by
            )
        return await self._note_repo.search(
            couple_id,
            query,
            created_by=created_by,
            limit=limit,
            offset=offset,
        )

    async def update_note(
        self,
        couple_id: int,
        user_id: int,
        note_id: int,
        title: str | None = None,
        content: str | None = None,
    ):
        note = await self._validate_note_access(couple_id, user_id, note_id)
        if title is not None:
            if not title.strip():
                raise ValidationError(
                    "Note title cannot be empty", field="title"
                )
            note.title = title.strip()
        if content is not None:
            note.content = content
        return await self._note_repo.update(note)

    async def delete_note(
        self, couple_id: int, user_id: int, note_id: int
    ) -> None:
        note = await self._validate_note_access(couple_id, user_id, note_id)
        await self._note_repo.delete(note)
        logger.info(
            "Deleted note id=%s from couple id=%s by user id=%s",
            note_id, couple_id, user_id,
        )