"""DFD loader (ARCHITECTURE §4.10): a new workbook built from the export template.

The sheet, the header row and the columns (order, type, display format) come only from
`export_template.md`; one row per included record follows. Only `output.value` is written,
unchanged: a format sets how Excel shows a value and never rounds it. A number column holding
a plain number gets a number, and a date column holding an ISO date (YYYY-MM-DD) gets a date;
anything else stays text (validation flagged it as WRONG_TYPE).
Extracted, generated and derived fields are written; the fields the tool does not fill
(`blank_for_now`, `system`) are exported blank.
"""

from collections.abc import Sequence
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE, Cell, MergedCell
from openpyxl.styles import Font
from openpyxl.worksheet.worksheet import Worksheet

from app.config.business_rules import BusinessRules, FieldDefinition
from app.config.export_template import ExportColumn, ExportTemplate
from app.contracts.record import StoredRecord
from app.validation.field_checks import is_right_type

HEADER_ROW = 1
FIRST_DATA_ROW = 2
# Freezing at A2 keeps row 1 (the headers) in view
FROZEN_HEADER_CELL = "A2"
NUMBER_TYPE = "number"
DATE_TYPE = "date"

# Roles whose output.value is exported; `system` and `blank_for_now` fields are exported blank
EXPORTED_ROLES = ("extracted", "generated", "derived")

# openpyxl reads text starting with "=" as a formula; such values are forced to plain text
FORMULA_START = "="
TEXT_DATA_TYPE = "s"

# A loader cell value: text, a number, or blank
LoaderValue = str | int | float | date | None


def write_loader(
    template: ExportTemplate,
    business_rules: BusinessRules,
    records: Sequence[StoredRecord],
    target: Path,
) -> int:
    """Build the loader from the template, one row per included record; return the row count."""
    workbook = Workbook()
    sheet = workbook.active
    if not isinstance(sheet, Worksheet):
        raise ValueError("The new workbook has no sheet to write the loader to.")
    sheet.title = template.sheet.name
    write_header(sheet, template)
    # Each template column is filled from the field definition with the same column name
    rules_by_column = {rule.column: rule for rule in business_rules.fields}
    included = [record for record in records if record.exclusion is None]
    for row_number, record in enumerate(included, start=FIRST_DATA_ROW):
        for column_number, column in enumerate(template.columns, start=1):
            cell = find_cell(sheet, row_number, column_number)
            write_cell(cell, find_loader_value(column, rules_by_column[column.name], record))
            cell.number_format = column.excel_format()
    workbook.save(target)
    return len(included)


def write_header(sheet: Worksheet, template: ExportTemplate) -> None:
    """Write the header row in template order, bold and frozen as the template says."""
    for column_number, header in enumerate(template.headers, start=1):
        cell = find_cell(sheet, HEADER_ROW, column_number)
        cell.value = header
        cell.font = Font(bold=template.sheet.is_header_bold)
    if template.sheet.is_header_frozen:
        sheet.freeze_panes = FROZEN_HEADER_CELL


def find_export_text(rule: FieldDefinition, record: StoredRecord) -> str | None:
    """Return the text a field exports: its output value, or None for blank and unfilled fields."""
    stored = record.fields.get(rule.key)
    if rule.role not in EXPORTED_ROLES or stored is None or not stored.output.value:
        return None
    return stored.output.value


def find_loader_value(
    column: ExportColumn, rule: FieldDefinition, record: StoredRecord
) -> LoaderValue:
    """Return a cell value: a number or date when the text is one, else the text unchanged."""
    text = find_export_text(rule, record)
    if text is not None and column.type == NUMBER_TYPE and is_right_type(rule, text):
        return float(text) if "." in text else int(text)
    if text is not None and column.type == DATE_TYPE:
        return read_iso_date(text)
    return text


def read_iso_date(text: str) -> date | str:
    """Return an ISO date (YYYY-MM-DD) as a date, so its format applies; other text stays text."""
    try:
        return date.fromisoformat(text)
    except ValueError:
        return text


def find_cell(sheet: Worksheet, row: int, column: int) -> Cell:
    """Return a writable cell; a merged cell cannot hold a value, so it is refused."""
    cell = sheet.cell(row=row, column=column)
    if isinstance(cell, MergedCell):
        raise ValueError(
            f"Cell {cell.coordinate} of sheet '{sheet.title}' is merged and cannot hold a value. "
            "Unmerge the cells."
        )
    return cell


def remove_illegal_characters(value: LoaderValue) -> LoaderValue:
    """Return text without the control characters an Excel file cannot hold."""
    if isinstance(value, str):
        return ILLEGAL_CHARACTERS_RE.sub("", value)
    return value


def write_cell(cell: Cell, value: LoaderValue) -> None:
    """Write a value to a cell, keeping text that starts with "=" as text, not a formula.

    Every cell of the loader and the audit workbook goes through here, so a control character
    (for example from PDF text) is removed at write time instead of crashing the export.
    """
    cell.value = remove_illegal_characters(value)
    if isinstance(value, str) and value.startswith(FORMULA_START):
        cell.data_type = TEXT_DATA_TYPE
