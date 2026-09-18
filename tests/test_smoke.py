from __future__ import annotations

from sqlalchemy import inspect

from app.database import engine, init_database
from app.handlers.crud import router as crud_router


async def test_database_schema_and_crud_router_are_available() -> None:
    await init_database()
    async with engine.connect() as connection:
        table_names = await connection.run_sync(
            lambda sync_connection: set(inspect(sync_connection).get_table_names())
        )

    assert {"users", "couples", "tasks", "movies", "lists"} <= table_names
    assert crud_router.message.handlers
    assert crud_router.callback_query.handlers
