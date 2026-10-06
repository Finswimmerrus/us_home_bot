from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from app.utils.markdown_table import (
    TableTooLargeError,
    _font_candidates,
    _load_font,
    parse_markdown_table,
    render_table_png,
)


def test_parse_standard_markdown_table() -> None:
    table = parse_markdown_table(
        "| Товар | Количество | Цена |\n"
        "|:------|:----------:|-----:|\n"
        "| Кофе | 2 | 900 ₽ |\n"
        "| Чай | 1 | 350 ₽ |"
    )

    assert table is not None
    assert table.rows[0] == ("Товар", "Количество", "Цена")
    assert table.rows[1] == ("Кофе", "2", "900 ₽")
    assert table.alignments == ("left", "center", "right")


def test_parse_table_from_code_fence_without_separator() -> None:
    table = parse_markdown_table("```text\nИмя | Город\nАнна | Москва\nИван | Казань\n```")

    assert table is not None
    assert table.rows == (
        ("Имя", "Город"),
        ("Анна", "Москва"),
        ("Иван", "Казань"),
    )


def test_ignore_non_table_text() -> None:
    assert parse_markdown_table("Одна строка | ещё текст") is None
    assert parse_markdown_table("обычное сообщение") is None


def test_reject_too_many_columns() -> None:
    row = "|".join(str(index) for index in range(13))
    with pytest.raises(TableTooLargeError):
        parse_markdown_table(f"{row}\n{row}")


def test_render_table_as_png() -> None:
    table = parse_markdown_table("Название | Значение\nКириллица | 42")
    assert table is not None

    content = render_table_png(table)
    image = Image.open(BytesIO(content))

    assert image.format == "PNG"
    assert image.width > 300
    assert image.height > 100


def test_bundled_font_supports_cyrillic() -> None:
    regular_font = _font_candidates(False)[0]
    bold_font = _font_candidates(True)[0]

    assert regular_font.exists()
    assert bold_font.exists()
    assert _load_font(28).getbbox("Кириллица") is not None
