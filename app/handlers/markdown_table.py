from __future__ import annotations

import asyncio

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.types import BufferedInputFile, Message

from app.utils.markdown_table import (
    TableTooLargeError,
    parse_markdown_table,
    render_table_png,
)

router = Router()


def _contains_markdown_table(message: Message) -> bool:
    if not message.text:
        return False
    try:
        return parse_markdown_table(message.text) is not None
    except TableTooLargeError:
        return True


@router.message(StateFilter(None), _contains_markdown_table)
async def markdown_table_to_image(message: Message) -> None:
    try:
        table = parse_markdown_table(message.text or "")
        if table is None:
            return
        image = await asyncio.to_thread(render_table_png, table)
    except TableTooLargeError as exc:
        await message.answer(str(exc))
        return

    await message.answer_photo(
        BufferedInputFile(image, filename="markdown-table.png"),
        caption="Таблица из Markdown",
    )
