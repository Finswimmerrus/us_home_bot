from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from aiogram.enums import ChatType
from aiogram.types import Chat, Message
from aiogram.types import User as TelegramUser
from sqlalchemy import func, select, text

from app.database import SessionLocal
from app.exceptions import CoupleFull
from app.handlers import crud
from app.handlers.sections import paginate, pagination_row
from app.middleware.private_chat_mw import PrivateChatMiddleware
from app.models.task import Task
from app.services.couple_service import CoupleService
from app.services.list_service import ListService
from app.services.task_service import TaskService
from app.utils.context import Context


async def _create_pair(session, telegram_id: int = 1):
    service = CoupleService(session)
    user = await service.get_or_create_user(telegram_id, first_name="Owner")
    couple, _ = await service.create_couple(user, "Test pair")
    return service, user, couple


async def test_sqlite_foreign_keys_and_cascade_delete() -> None:
    async with SessionLocal() as session:
        service, user, couple = await _create_pair(session)
        await TaskService(session).create_task(couple.id, user.id, "Private task")
        created_list = await ListService(session).create_list(couple.id, user.id, "Shopping")
        await ListService(session).add_item(
            couple.id, user.id, created_list.id, "Milk"
        )
        assert await session.scalar(text("PRAGMA foreign_keys")) == 1
        await service.delete_couple(couple.id, user.id)
        await session.flush()
        assert await session.scalar(select(func.count(Task.id))) == 0


async def test_invitation_can_only_be_claimed_once() -> None:
    async with SessionLocal() as session:
        service, _, couple = await _create_pair(session)
        first = await service.get_or_create_user(2)
        second = await service.get_or_create_user(3)
        invite_code = couple.invite_code
        assert invite_code
        stale_couple = SimpleNamespace(id=couple.id, invite_code=invite_code)

        assert await service.join_couple(first, couple) is not None
        with pytest.raises(CoupleFull):
            await service.join_couple(second, stale_couple)


async def test_private_chat_middleware_ignores_group_messages() -> None:
    middleware = PrivateChatMiddleware()
    handler = AsyncMock(return_value="handled")
    user = TelegramUser(id=1, is_bot=False, first_name="User")
    group_message = Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=-1, type=ChatType.GROUP, title="Group"),
        from_user=user,
        text="Заметки",
    )
    private_message = Message(
        message_id=2,
        date=datetime.now(UTC),
        chat=Chat(id=1, type=ChatType.PRIVATE, first_name="User"),
        from_user=user,
        text="Заметки",
    )

    assert await middleware(handler, group_message, {}) is None
    assert await middleware(handler, private_message, {}) == "handled"
    handler.assert_awaited_once()


def test_pagination_keeps_records_after_first_page() -> None:
    items = list(range(21))
    page_items, page, page_count = paginate(items, 1)

    assert page_items == list(range(10, 20))
    assert ("Назад", "notes:list:0") in pagination_row(
        "notes:list", page, page_count
    )
    assert ("Далее", "notes:list:2") in pagination_row(
        "notes:list", page, page_count
    )


async def test_due_today_uses_full_sqlite_date() -> None:
    async with SessionLocal() as session:
        _, user, couple = await _create_pair(session)
        now = datetime.now()
        await TaskService(session).create_task(
            couple.id, user.id, "Today", due_at=now
        )
        await TaskService(session).create_task(
            couple.id, user.id, "Tomorrow", due_at=now + timedelta(days=1)
        )

        tasks = await TaskService(session).get_today_tasks(couple.id, user.id)
        assert [task.title for task in tasks] == ["Today"]


async def test_stale_challenge_confirmation_is_handled(monkeypatch) -> None:
    state = AsyncMock()
    state.get_data.return_value = {}
    alert = AsyncMock()
    monkeypatch.setattr(crud, "alert_callback", alert)
    callback = SimpleNamespace(data="chl:new:confirm")

    await crud.cb_challenge_create_confirm(
        callback,
        Context(user_id=1),
        session=None,
        state=state,
    )

    state.clear.assert_awaited_once()
    alert.assert_awaited_once()


def test_context_uses_configured_timezone() -> None:
    context = Context(user_id=1, timezone="Europe/Moscow")
    assert context.local_date() == datetime.now(ZoneInfo("Europe/Moscow")).date()


def test_detail_cards_include_saved_text_and_links() -> None:
    item = SimpleNamespace(
        id=1,
        title="Gift",
        status="WANTED",
        price=None,
        description="Details",
        url="https://example.com/gift",
    )
    task = SimpleNamespace(
        id=1,
        title="Task",
        status="TODO",
        priority="NORMAL",
        assigned_to=None,
        due_at=None,
        description="Task details",
    )

    assert "Details" in crud._wish_text(item)
    assert item.url in crud._wish_text(item)
    assert "Task details" in crud._task_text(task)
