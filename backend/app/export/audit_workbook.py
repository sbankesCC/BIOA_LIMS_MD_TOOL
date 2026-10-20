"""Audit workbook (CONTRACTS §8): writes the five audit sheets to an Excel file.

Each sheet has a header row, then one row per item. The record name column takes its header
from the field rules (the first loader column), so no client column name is written here.
"""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from pydantic import BaseModel

from app.export.audit_rows import AuditRows
from app.export.loader import LoaderValue, find_cell, write_cell

SUMMARY_SHEET = "Summary"
VALUES_SHEET = "Values"
EDITS_SHEET = "Edits"
EXCLUDED_SHEET = "Excluded"
RUN_ISSUES_SHEET = "Run issues"

SUMMARY_HEADERS = ["Setting", "Value"]
EXCLUDED_HEADERS = ["Record ID", "Name", "Found in", "Excluded by", "At", "Reason"]
RUN_ISSUE_HEADERS = ["Code", "Message"]


def make_value_headers(name_column: str) -> list[str]:
    """Return the Values sheet headers; the record name column is named after its field."""
    return [
        "Record ID",
        name_column,
        "Field",
        "Exported value",
        "Origin",
        "Source document",
        "Location",
        "Source quote",
        "Extraction status",
        "Citation check",
        "Verification verdict",
        "Issue codes",
        "Issue outcome",
    ]


def make_edit_headers(name_column: str) -> list[str]:
    """Return the Edits sheet headers; the record name column is named after its field."""
    return [
        "Change ID",
        "Record ID",
        name_column,
        "Field",
        "Type",
        "Old value",
        "New value",
        "Reason",
        "User",
        "Time",
        "Bulk ID",
    ]


def write_audit_workbook(rows: AuditRows, name_column: str, target: Path) -> None:
    """Write the five audit sheets, in CONTRACTS order, to `target`."""
    workbook = Workbook()
    # The new workbook's default sheet is removed; every sheet is added by name
    default_sheet = workbook.active
    if default_sheet is not None:
        workbook.remove(default_sheet)
    sheets: list[tuple[str, list[str], Sequence[BaseModel]]] = [
        (SUMMARY_SHEET, SUMMARY_HEADERS, rows.summary),
        (VALUES_SHEET, make_value_headers(name_column), rows.values),
        (EDITS_SHEET, make_edit_headers(name_column), rows.edits),
        (EXCLUDED_SHEET, EXCLUDED_HEADERS, rows.excluded),
        (RUN_ISSUES_SHEET, RUN_ISSUE_HEADERS, rows.run_issues),
    ]
    for title, headers, sheet_rows in sheets:
        write_sheet(workbook, title, headers, sheet_rows)
    workbook.save(target)


def write_sheet(
    workbook: Workbook, title: str, headers: list[str], rows: Sequence[BaseModel]
) -> None:
    """Add one sheet: the header row, then each row's values in model field order."""
    sheet = workbook.create_sheet(title)
    sheet.append(headers)
    for row_number, row in enumerate(rows, start=2):
        values = [to_cell_value(value) for value in row.model_dump().values()]
        for column_number, value in enumerate(values, start=1):
            write_cell(find_cell(sheet, row_number, column_number), value)


def to_cell_value(value: object) -> LoaderValue:
    """Return a value Excel can hold: times as ISO text (Excel has no time zones), text as is."""
    if value is None or isinstance(value, (str, int, float)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
