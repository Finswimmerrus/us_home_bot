from __future__ import annotations

from app.models.couple import Couple
from app.models.couple_member import CoupleMember
from app.models.list import List
from app.models.list_item import ListItem
from app.models.movie import Movie
from app.models.movie_rating import MovieRating
from app.models.note import Note
from app.models.task import Task
from app.models.trip import Trip, TripPlace
from app.models.user import User
from app.models.wishlist import WishlistItem

__all__ = [
    "User",
    "Couple",
    "CoupleMember",
    "Task",
    "Movie",
    "MovieRating",
    "List",
    "ListItem",
    "Trip",
    "TripPlace",
    "WishlistItem",
    "Note",
]
