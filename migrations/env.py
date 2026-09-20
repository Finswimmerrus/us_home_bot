from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection

from app.config import config as app_config
from app.database import Base

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from app.models.challenge import Challenge, ChallengeEntry, ChallengeParticipant  # noqa: E402
from app.models.couple import Couple  # noqa: E402
from app.models.couple_member import CoupleMember  # noqa: E402
from app.models.list import List  # noqa: E402
from app.models.list_item import ListItem  # noqa: E402
from app.models.movie import Movie  # noqa: E402
from app.models.movie_rating import MovieRating  # noqa: E402
from app.models.note import Note  # noqa: E402
from app.models.task import Task  # noqa: E402
from app.models.trip import Trip, TripPlace  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.wishlist import WishlistItem  # noqa: E402

target_metadata = Base.metadata

config.set_main_option("sqlalchemy.url", app_config.DATABASE_URL)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations against an async connection."""
    from sqlalchemy.ext.asyncio import create_async_engine

    connectable = create_async_engine(
        app_config.DATABASE_URL,
        poolclass=pool.NullPool,
        future=True,
    )
    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


def run_migrations() -> None:
    """Entry point used by Alembic."""
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        asyncio.run(run_async_migrations())


run_migrations()
