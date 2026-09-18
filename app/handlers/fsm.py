from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage


class TaskCreateFSM(StatesGroup):
    title = State()
    description = State()
    priority = State()
    assigned_to = State()
    due_at = State()
    confirm = State()


class TaskEditFSM(StatesGroup):
    field = State()
    value = State()


class MovieCreateFSM(StatesGroup):
    title = State()
    description = State()


class ListCreateFSM(StatesGroup):
    name = State()


class ListItemCreateFSM(StatesGroup):
    title = State()


class TripCreateFSM(StatesGroup):
    title = State()
    description = State()


class PlaceCreateFSM(StatesGroup):
    title = State()
    description = State()


class WishlistCreateFSM(StatesGroup):
    title = State()
    url = State()


class NoteCreateFSM(StatesGroup):
    title = State()
    content = State()


class SettingsDisplayFSM(StatesGroup):
    display_name = State()


class SettingsTimezoneFSM(StatesGroup):
    timezone = State()


class CoupleNameFSM(StatesGroup):
    name = State()


class MovieEditFSM(StatesGroup):
    field = State()
    value = State()


class MovieRatingFSM(StatesGroup):
    rating = State()


class NoteEditFSM(StatesGroup):
    field = State()
    value = State()


class ListEditFSM(StatesGroup):
    field = State()
    value = State()


class TripEditFSM(StatesGroup):
    field = State()
    value = State()


class TaskAssignFSM(StatesGroup):
    user_id = State()


storage = MemoryStorage()
