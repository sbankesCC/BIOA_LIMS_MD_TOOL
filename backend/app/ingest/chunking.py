"""Shared chunking rules for every reader: chunk sizes, stable chunk IDs and table row groups.

Chunk IDs depend only on the document ID and positions in the document, so ingesting the same
file again gives the same IDs (CONTRACTS §1).
"""

from collections.abc import Sequence

# A Word section longer than this is split at paragraph boundaries (never inside a paragraph)
MAX_TEXT_CHUNK_CHARACTERS = 4000

# Tables keep all their rows in one chunk up to this many data rows; larger tables are split
# into groups of this size, each starting with the header row again
MAX_TABLE_ROWS_PER_CHUNK = 50

# Spreadsheet rows per chunk (data rows; the header row is repeated in every later chunk)
MAX_SHEET_ROWS_PER_CHUNK = 50

# How cells of one table or sheet row are joined into a line of chunk text
CELL_SEPARATOR = " | "


class ChunkIdCounter:
    """Numbers the chunks of one document in reading order: `doc01-c001`, `doc02-p04-c007`."""

    def __init__(self, document_id: str) -> None:
        """Start counting at 1 for this document."""
        self.document_id = document_id
        self.last_number = 0

    def next_id(self, page: int | None = None) -> str:
        """Return the next chunk ID; PDF chunks include their page number."""
        self.last_number += 1
        number = f"c{self.last_number:03d}"
        if page is None:
            return f"{self.document_id}-{number}"
        return f"{self.document_id}-p{page:02d}-{number}"


def format_row(cells: Sequence[str]) -> str:
    """Join one row's cell texts into a line of chunk text."""
    return CELL_SEPARATOR.join(cells)


def is_blank_row(cells: Sequence[str]) -> bool:
    """Return True when every cell of a row is empty or only spaces."""
    return all(cell.strip() == "" for cell in cells)


def group_paragraphs(paragraphs: list[str], max_characters: int) -> list[list[str]]:
    """Split a section's paragraphs into groups of at most `max_characters` (whole paragraphs)."""
    groups: list[list[str]] = []
    current: list[str] = []
    current_size = 0
    for paragraph in paragraphs:
        # Start a new group when this paragraph would make the current one too long
        if current and current_size + len(paragraph) > max_characters:
            groups.append(current)
            current, current_size = [], 0
        current.append(paragraph)
        current_size += len(paragraph)
    if current:
        groups.append(current)
    return groups


def split_table_rows(rows: list[str], max_rows: int) -> list[list[str]]:
    """Keep a table whole, or split a very large one into groups that repeat the header row."""
    header, data_rows = rows[0], rows[1:]
    if len(data_rows) <= max_rows:
        return [rows]
    return [
        [header, *data_rows[start : start + max_rows]]
        for start in range(0, len(data_rows), max_rows)
    ]
