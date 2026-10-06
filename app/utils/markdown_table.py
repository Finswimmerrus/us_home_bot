from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

MAX_COLUMNS = 12
MAX_ROWS = 50
MAX_CELL_LENGTH = 300
MAX_IMAGE_HEIGHT = 9_000

_SEPARATOR_RE = re.compile(r"^:?-{3,}:?$")
_CODE_FENCE_RE = re.compile(r"^\s*```[^\n]*\n(?P<body>.*)\n\s*```\s*$", re.DOTALL)
_INLINE_LINK_RE = re.compile(r"\[([^]]+)]\([^)]*\)")


class TableTooLargeError(ValueError):
    """Raised when a valid table cannot safely be rendered as a Telegram photo."""


@dataclass(frozen=True, slots=True)
class MarkdownTable:
    rows: tuple[tuple[str, ...], ...]
    alignments: tuple[str, ...]
    has_header: bool = True

    @property
    def column_count(self) -> int:
        return len(self.rows[0])


def _strip_fence(text: str) -> str:
    match = _CODE_FENCE_RE.match(text.strip())
    return match.group("body") if match else text


def _split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith(r"\|"):
        line = line[:-1]

    cells: list[str] = []
    cell: list[str] = []
    escaped = False
    for character in line:
        if escaped:
            cell.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == "|":
            cells.append("".join(cell).strip())
            cell = []
        else:
            cell.append(character)
    if escaped:
        cell.append("\\")
    cells.append("".join(cell).strip())
    return cells


def _clean_inline_markdown(value: str) -> str:
    value = _INLINE_LINK_RE.sub(r"\1", value)
    value = re.sub(r"(?<!\\)(?:\*\*|__|~~|`)", "", value)
    value = re.sub(r"(?<!\\)(?:\*|_)", "", value)
    return value.replace(r"\|", "|").replace(r"\\", "\\").strip()


def _table_blocks(text: str) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in _strip_fence(text).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if "|" in line:
            current.append(line)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def parse_markdown_table(text: str) -> MarkdownTable | None:
    """Return the first Markdown-like pipe table found in *text*."""
    for block in _table_blocks(text):
        if len(block) < 2:
            continue
        raw_rows = [_split_row(line) for line in block]
        column_count = max(len(row) for row in raw_rows)
        if column_count < 2 or any(len(row) != column_count for row in raw_rows):
            continue

        separator_index: int | None = None
        alignments = ["left"] * column_count
        if len(raw_rows) >= 2 and all(
            _SEPARATOR_RE.fullmatch(cell.replace(" ", "")) for cell in raw_rows[1]
        ):
            separator_index = 1
            for index, cell in enumerate(raw_rows[1]):
                marker = cell.replace(" ", "")
                if marker.startswith(":") and marker.endswith(":"):
                    alignments[index] = "center"
                elif marker.endswith(":"):
                    alignments[index] = "right"

        content_rows = [row for index, row in enumerate(raw_rows) if index != separator_index]
        if len(content_rows) < 2:
            continue
        if column_count > MAX_COLUMNS or len(content_rows) > MAX_ROWS:
            raise TableTooLargeError(
                f"Поддерживается не больше {MAX_COLUMNS} столбцов и {MAX_ROWS} строк."
            )

        cleaned_rows = tuple(
            tuple(_clean_inline_markdown(cell) for cell in row) for row in content_rows
        )
        if any(len(cell) > MAX_CELL_LENGTH for row in cleaned_rows for cell in row):
            raise TableTooLargeError(
                f"Ячейка таблицы не должна быть длиннее {MAX_CELL_LENGTH} символов."
            )
        return MarkdownTable(rows=cleaned_rows, alignments=tuple(alignments))
    return None


def _font_candidates(bold: bool) -> tuple[Path, ...]:
    filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    windows_filename = "arialbd.ttf" if bold else "arial.ttf"
    return (
        Path("/usr/share/fonts/truetype/dejavu") / filename,
        Path("/usr/share/fonts/truetype/dejavu") / filename,
        Path("C:/Windows/Fonts") / windows_filename,
    )


def _load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _font_candidates(bold):
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    try:
        return ImageFont.truetype(
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size=size
        )
    except OSError:
        return ImageFont.load_default(size=size)


def _text_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> int:
    return int(draw.textlength(text or " ", font=font))


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    if not text:
        return [""]
    result: list[str] = []
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split(" ")
        line = ""
        for word in words:
            candidate = word if not line else f"{line} {word}"
            if _text_width(draw, candidate, font) <= max_width:
                line = candidate
                continue
            if line:
                result.append(line)
                line = ""
            while word and _text_width(draw, word, font) > max_width:
                cut = max(1, len(word) - 1)
                while cut > 1 and _text_width(draw, word[:cut], font) > max_width:
                    cut -= 1
                result.append(word[:cut])
                word = word[cut:]
            line = word
        result.append(line)
    return result


def render_table_png(table: MarkdownTable) -> bytes:
    """Render a parsed Markdown table into a styled PNG byte string."""
    font = _load_font(28)
    header_font = _load_font(28, bold=True)
    probe = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(probe)
    horizontal_padding = 24
    vertical_padding = 18
    line_height = 38

    widths: list[int] = []
    for column in range(table.column_count):
        measured = max(
            _text_width(draw, row[column], header_font if index == 0 else font)
            for index, row in enumerate(table.rows)
        )
        widths.append(min(max(measured + horizontal_padding * 2, 140), 420))

    max_table_width = 2_400
    if sum(widths) > max_table_width:
        scale = max_table_width / sum(widths)
        widths = [max(100, int(width * scale)) for width in widths]

    wrapped_rows: list[list[list[str]]] = []
    row_heights: list[int] = []
    for row_index, row in enumerate(table.rows):
        row_font = header_font if row_index == 0 else font
        wrapped = [
            _wrap_text(draw, cell, row_font, widths[index] - horizontal_padding * 2)
            for index, cell in enumerate(row)
        ]
        wrapped_rows.append(wrapped)
        row_heights.append(max(len(lines) for lines in wrapped) * line_height + vertical_padding * 2)

    margin = 28
    image_width = sum(widths) + margin * 2
    image_height = sum(row_heights) + margin * 2
    if image_height > MAX_IMAGE_HEIGHT:
        raise TableTooLargeError("Таблица получается слишком высокой для изображения.")

    image = Image.new("RGB", (image_width, image_height), "#f1f5f9")
    draw = ImageDraw.Draw(image)
    y = margin
    for row_index, (wrapped, row_height) in enumerate(zip(wrapped_rows, row_heights, strict=True)):
        background = "#334155" if row_index == 0 else ("#ffffff" if row_index % 2 else "#f8fafc")
        foreground = "#ffffff" if row_index == 0 else "#0f172a"
        row_font = header_font if row_index == 0 else font
        x = margin
        for column, lines in enumerate(wrapped):
            width = widths[column]
            draw.rectangle((x, y, x + width, y + row_height), fill=background, outline="#cbd5e1", width=2)
            text_y = y + vertical_padding
            for line in lines:
                text_width = _text_width(draw, line, row_font)
                alignment = table.alignments[column]
                if alignment == "right":
                    text_x = float(x + width - horizontal_padding - text_width)
                elif alignment == "center":
                    text_x = x + (width - text_width) / 2
                else:
                    text_x = float(x + horizontal_padding)
                draw.text((text_x, text_y), line, font=row_font, fill=foreground)
                text_y += line_height
            x += width
        y += row_height

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
