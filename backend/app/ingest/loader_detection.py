"""Loader detection: an uploaded DFD loader or earlier export is not a source document.

A workbook is a loader when the header row of any sheet holds every DFD column name. The column
names come from the client's DFD template, never from code.
"""

from collections.abc import Sequence

from app.ingest.xlsx import SheetContent


def is_loader_header(cells: Sequence[str], dfd_headers: Sequence[str]) -> bool:
    """Return True when a header row contains every DFD column name (extra columns allowed)."""
    if not dfd_headers:
        return False
    found = {cell.strip() for cell in cells}
    return set(dfd_headers) <= found


def is_loader_workbook(sheets: Sequence[SheetContent], dfd_headers: Sequence[str]) -> bool:
    """Return True when the first non-blank row of any sheet is a DFD loader header row."""
    for sheet in sheets:
        if sheet.rows and is_loader_header(sheet.rows[0].cells, dfd_headers):
            return True
    return False
