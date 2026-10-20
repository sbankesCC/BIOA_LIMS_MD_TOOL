"""Excel reader: each sheet split into row ranges as `sheet_rows` chunks (`doc03-sReagents-r12-20`).

The first non-blank row of a sheet is taken as its header and repeated at the top of later chunks.
Cell values are the saved values (formulas are not recalculated).
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path

from openpyxl import load_workbook

from app.contracts.chunk import Chunk
from app.ingest.chunking import MAX_SHEET_ROWS_PER_CHUNK, format_row, is_blank_row

# Characters kept from a sheet name in chunk IDs; everything else is dropped
SHEET_ID_PATTERN = re.compile(r"[^A-Za-z0-9]")


@dataclass
class SheetRow:
    """One non-blank sheet row: its Excel row number and its cell texts."""

    number: int
    cells: list[str]


@dataclass
class SheetContent:
    """One sheet's name and its non-blank rows (the first is the header row)."""

    name: str
    rows: list[SheetRow]


def read_workbook_sheets(path: Path) -> list[SheetContent]:
    """Read every worksheet's non-blank rows as text."""
    workbook = load_workbook(path, data_only=True)
    try:
        return [read_sheet(sheet.title, sheet.iter_rows(values_only=True)) for sheet in workbook]
    finally:
        workbook.close()


def read_sheet(name: str, rows: Iterable[tuple[object, ...]]) -> SheetContent:
    """Turn a sheet's row values into numbered text rows, skipping blank rows."""
    content = SheetContent(name=name, rows=[])
    for number, values in enumerate(rows, start=1):
        cells = trim_trailing_blanks([format_cell(value) for value in values])
        if not is_blank_row(cells):
            content.rows.append(SheetRow(number=number, cells=cells))
    return content


def format_cell(value: object) -> str:
    """Return a cell value as text as close to the saved value as possible."""
    if value is None:
        return ""
    # Whole numbers stored as floats show without ".0"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    # Dates without a time show as the date only
    if isinstance(value, datetime) and value.time() == time(0, 0):
        return value.date().isoformat()
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    # A line break inside a cell would break the one-line-per-row layout
    return " ".join(str(value).splitlines())


def trim_trailing_blanks(cells: list[str]) -> list[str]:
    """Drop empty cells at the end of a row."""
    while cells and cells[-1].strip() == "":
        cells.pop()
    return cells


def make_sheet_chunks(sheets: list[SheetContent], document_id: str) -> list[Chunk]:
    """Split every sheet into row-range chunks with stable IDs."""
    chunks: list[Chunk] = []
    used_tokens: set[str] = set()
    for index, sheet in enumerate(sheets, start=1):
        token = make_sheet_token(sheet.name, index, used_tokens)
        chunks.extend(make_chunks_for_sheet(sheet, document_id, token))
    return chunks


def make_sheet_token(name: str, index: int, used_tokens: set[str]) -> str:
    """Return the sheet part of chunk IDs: `s` + the name's letters and digits, kept unique."""
    token = "s" + (SHEET_ID_PATTERN.sub("", name) or str(index))
    # Two names that clean to the same token get the sheet's position added
    if token in used_tokens:
        token = f"{token}{index}"
    used_tokens.add(token)
    return token


def make_chunks_for_sheet(sheet: SheetContent, document_id: str, token: str) -> list[Chunk]:
    """Split one sheet into groups of rows; later groups start with the header row again."""
    if not sheet.rows:
        return []
    header, data_rows = sheet.rows[0], sheet.rows[1:]
    size = MAX_SHEET_ROWS_PER_CHUNK
    # A sheet with only a header row still gives one chunk
    starts = range(0, len(data_rows), size) if data_rows else range(1)
    groups: list[list[SheetRow]] = [data_rows[start : start + size] for start in starts]
    chunks: list[Chunk] = []
    for position, group in enumerate(groups):
        rows = [header, *group]
        # The first group includes the header row itself, so its row range starts there
        first_number = header.number if position == 0 else group[0].number
        row_range = f"{first_number}-{rows[-1].number}"
        text = "\n".join(format_row(row.cells) for row in rows)
        chunks.append(make_sheet_chunk(document_id, token, sheet.name, row_range, text))
    return chunks


def make_sheet_chunk(
    document_id: str, token: str, sheet_name: str, row_range: str, text: str
) -> Chunk:
    """Build one `sheet_rows` chunk."""
    return Chunk(
        chunk_id=f"{document_id}-{token}-r{row_range}",
        document_id=document_id,
        page=None,
        section=None,
        sheet=sheet_name,
        row_range=row_range,
        kind="sheet_rows",
        is_scanned=False,
        text=text,
        image_ref=None,
    )
