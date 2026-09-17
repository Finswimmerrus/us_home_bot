from __future__ import annotations

import logging

from app.config import config
from app.database import SessionLocal, engine, get_session

logger = logging.getLogger(__name__)


async def init_db() -> None:
    """Apply Alembic migrations to the configured DATABASE_URL."""
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", config.DATABASE_URL)
    command.upgrade(alembic_cfg, "head")
    logger.info("Database migrations applied")


async def close_db() -> None:
    """Dispose engine and release connection pool resources."""
    await engine.dispose()


__all__ = ["init_db", "close_db", "get_session", "SessionLocal"]
