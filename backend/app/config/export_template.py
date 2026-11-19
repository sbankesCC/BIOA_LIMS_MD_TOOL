"""Export template (`export_template.md`): the loader sheet and its columns, in export order.

Export builds the loader workbook from this file alone, and it is the only source of column
order. A column's format only sets how Excel shows a value; values are written unchanged.
"""

import re
from pathlib import Path
from typing import Literal, get_args

from pydantic import BaseModel, Field

from app.config.business_rules import FILE_NAME as BUSINESS_RULES_FILE
from app.config.business_rules import (
    NO,
    VERSION_ROW,
    YES,
    BusinessRules,
    RawTable,
    build_raw_table,
)
from app.config.business_rules_checks import not_in_set, repeated
from app.config.errors import ConfigError, require_file

FILE_NAME = "export_template.md"

# Section headings and table headers code reads
SHEET_HEADING = "Sheet"
COLUMNS_HEADING = "Columns"
SETTING_HEADER = ["Setting", "Value"]
COLUMN_HEADER = ["Column", "Type", "Format"]
SHEET_NAME_SETTING = "Sheet name"
HEADER_BOLD_SETTING = "Header bold"
FREEZE_SETTING = "Freeze header row"
SETTINGS = (SHEET_NAME_SETTING, HEADER_BOLD_SETTING, FREEZE_SETTING)

ExportType = Literal["text", "number", "date"]
EXPORT_TYPES: tuple[str, ...] = get_args(ExportType)

# The export types each business rules field type may use (CONTRACTS §12)
EXPORT_TYPES_BY_FIELD_TYPE: dict[str, tuple[str, ...]] = {
    "decimal": ("number",),
    "integer": ("number",),
    "text": ("text", "date"),
    "boolean": ("text",),
}

# Formats: "<n> decimals" for numbers, a YYYY/MM/DD pattern for dates
DECIMALS_FORMAT = re.compile(r"^(?P<places>\d+) decimals?$")
DATE_FORMAT = re.compile(r"^(?=.*(?:YYYY|MM|DD))(?:YYYY|MM|DD|[/\-. ])+$")
EXCEL_DEFAULT_FORMAT = "General"

# Excel's limits on a sheet name
MAX_SHEET_NAME_LENGTH = 31
FORBIDDEN_SHEET_CHARACTERS = "[]:*?/\\"

# The table before the first `##` heading holds the version
PREAMBLE = ""


class SheetSettings(BaseModel):
    """The loader sheet: its name, and how the header row looks."""

    name: str = Field(min_length=1)
    is_header_bold: bool
    is_header_frozen: bool


class ExportColumn(BaseModel):
    """One loader column: header, export type and display format (blank: Excel's default)."""

    name: str = Field(min_length=1)
    type: ExportType
    format: str = ""

    def excel_format(self) -> str:
        """Return the Excel number format for this column's cells."""
        decimals = DECIMALS_FORMAT.match(self.format)
        if decimals is not None:
            places = int(decimals["places"])
            return "0." + "0" * places if places else "0"
        # A date pattern becomes Excel's lower-case tokens (YYYY → yyyy)
        return self.format.lower() if self.format else EXCEL_DEFAULT_FORMAT


class ExportTemplate(BaseModel):
    """The whole export template: version, sheet settings and columns in export order."""

    version: str = Field(min_length=1)
    sheet: SheetSettings
    columns: list[ExportColumn] = Field(min_length=1)

    @property
    def headers(self) -> list[str]:
        """Return the column headers in export order."""
        return [column.name for column in self.columns]


# ----- Loading -----


def load_export_template(path: Path) -> ExportTemplate:
    """Load `export_template.md` and check it on its own; raise ConfigError on any problem."""
    require_file(path)
    return parse_export_template(path.read_text(encoding="utf-8"))


def parse_export_template(text: str) -> ExportTemplate:
    """Read the file's tables, check them, then build the model."""
    tables = read_tables(text)
    problems = (
        find_version_problems(tables)
        + find_sheet_problems(tables.get(SHEET_HEADING))
        + find_column_problems(tables.get(COLUMNS_HEADING))
    )
    if problems:
        raise ConfigError(problems)
    return build_export_template(tables)


def read_tables(text: str) -> dict[str, RawTable]:
    """Return the first table under each `##` heading (the preamble's under an empty name)."""
    tables: dict[str, RawTable] = {}
    heading = PREAMBLE
    table_lines: list[tuple[int, str]] = []
    for line_number, line in enumerate([*text.splitlines(), ""], start=1):
        stripped = line.strip()
        if stripped.startswith("|"):
            table_lines.append((line_number, stripped))
            continue
        # A table ends at the first line that is not a table row
        if table_lines and heading not in tables:
            tables[heading] = build_raw_table(heading, table_lines)
        table_lines = []
        if stripped.startswith("## "):
            heading = stripped[3:].strip()
    return tables


def build_export_template(tables: dict[str, RawTable]) -> ExportTemplate:
    """Build the model from tables that passed the checks."""
    settings = {row[0]: row[1] for row in tables[SHEET_HEADING].rows}
    return ExportTemplate(
        version=read_template_version(tables) or "",
        sheet=SheetSettings(
            name=settings[SHEET_NAME_SETTING],
            is_header_bold=settings[HEADER_BOLD_SETTING] == YES,
            is_header_frozen=settings[FREEZE_SETTING] == YES,
        ),
        columns=[
            ExportColumn.model_validate({"name": name, "type": kind, "format": format_text})
            for name, kind, format_text in tables[COLUMNS_HEADING].rows
        ],
    )


def read_template_version(tables: dict[str, RawTable]) -> str | None:
    """Return the Version row of the first table, or None if there is none."""
    preamble = tables.get(PREAMBLE)
    rows = preamble.rows if preamble is not None else []
    return next(
        (row[1] for row in rows if len(row) >= 2 and row[0] == VERSION_ROW and row[1]), None
    )


# ----- Checks on this file -----


def find_version_problems(tables: dict[str, RawTable]) -> list[str]:
    """Check the first table has a Version row."""
    if read_template_version(tables) is None:
        return [f"{FILE_NAME}: the first table needs a 'Version' row with a value."]
    return []


def find_sheet_problems(table: RawTable | None) -> list[str]:
    """Check the Sheet table: each setting once, yes/no flags, and a name Excel accepts."""
    where = f"{FILE_NAME}: '## {SHEET_HEADING}'"
    if table is None or table.columns != SETTING_HEADER:
        return [f"{where} needs a 'Setting | Value' table."]
    if any(len(row) != len(SETTING_HEADER) for row in table.rows):
        return [f"{where}: every row needs two cells (Setting | Value)."]
    settings = {row[0]: row[1] for row in table.rows}
    problems = [
        f"{where} is missing the setting '{name}'." for name in SETTINGS if name not in settings
    ]
    problems += [
        f"{where} has an unknown setting '{name}'." for name in settings if name not in SETTINGS
    ]
    problems += [
        f"{where}: '{name}' is listed twice." for name in repeated([row[0] for row in table.rows])
    ]
    for name in (HEADER_BOLD_SETTING, FREEZE_SETTING):
        if name in settings:
            problems += not_in_set(where, name, settings[name], (YES, NO))
    return problems + find_sheet_name_problems(where, settings.get(SHEET_NAME_SETTING))


def find_sheet_name_problems(where: str, name: str | None) -> list[str]:
    """Check a sheet name is not empty, not too long, and has no character Excel forbids."""
    if not name:
        return [] if name is None else [f"{where}: '{SHEET_NAME_SETTING}' is empty."]
    problems: list[str] = []
    if len(name) > MAX_SHEET_NAME_LENGTH:
        problems.append(
            f"{where}: the sheet name is longer than {MAX_SHEET_NAME_LENGTH} characters."
        )
    if any(character in FORBIDDEN_SHEET_CHARACTERS for character in name):
        problems.append(
            f"{where}: the sheet name may not contain any of {FORBIDDEN_SHEET_CHARACTERS}."
        )
    return problems


def find_column_problems(table: RawTable | None) -> list[str]:
    """Check the Columns table: its header, three cells a row, unique names, known types."""
    where = f"{FILE_NAME}: '## {COLUMNS_HEADING}'"
    if table is None or table.columns != COLUMN_HEADER:
        return [f"{where} needs a 'Column | Type | Format' table."]
    if not table.rows:
        return [f"{where} has no columns."]
    problems: list[str] = []
    for row in table.rows:
        if len(row) != len(COLUMN_HEADER) or not row[0]:
            problems.append(
                f"{where}: the row '{' | '.join(row)}' needs a name, a type and a format cell."
            )
            continue
        problems += not_in_set(f"{where}: '{row[0]}'", "Type", row[1], EXPORT_TYPES)
        problems += find_format_problems(f"{where}: '{row[0]}'", row[1], row[2])
    names = [row[0] for row in table.rows if row]
    return problems + [f"{where}: the column '{name}' is listed twice." for name in repeated(names)]


def find_format_problems(where: str, export_type: str, format_text: str) -> list[str]:
    """Check a format fits its type: `<n> decimals` for numbers, a date pattern for dates."""
    if not format_text:
        return []
    if export_type == "number" and DECIMALS_FORMAT.match(format_text):
        return []
    if export_type == "date" and DATE_FORMAT.match(format_text):
        return []
    return [
        f"{where}: the format '{format_text}' does not fit type '{export_type}'. Use blank, "
        "'<n> decimals' for a number, or a pattern of YYYY, MM and DD for a date."
    ]


# ----- Cross-file checks (called by the config bundle) -----


def find_column_set_problems(template: ExportTemplate, business_rules: BusinessRules) -> list[str]:
    """Check the template's columns are exactly the loader columns of the business rules."""
    loader_columns = business_rules.columns()
    problems = [
        f"{FILE_NAME}: the loader column '{column}' of {BUSINESS_RULES_FILE} is missing. "
        "Add a row for it under '## Columns'."
        for column in loader_columns
        if column not in template.headers
    ]
    problems += [
        f"{FILE_NAME}: the column '{column}' is not a loader column in {BUSINESS_RULES_FILE}. "
        "Fix the name, or add the field to the business rules."
        for column in template.headers
        if column not in loader_columns
    ]
    return problems


def find_type_problems(template: ExportTemplate, business_rules: BusinessRules) -> list[str]:
    """Check each column's export type agrees with its field's type in the business rules."""
    types_by_column = {field.column: field.type for field in business_rules.fields}
    problems: list[str] = []
    for column in template.columns:
        field_type = types_by_column.get(column.name)
        allowed = EXPORT_TYPES_BY_FIELD_TYPE.get(field_type, ()) if field_type else None
        if allowed is not None and column.type not in allowed:
            problems.append(
                f"{FILE_NAME}: '{column.name}' is type '{column.type}', but the field is "
                f"'{field_type}' in {BUSINESS_RULES_FILE}. Use one of: {', '.join(allowed)}."
            )
    return problems


def order_fields(business_rules: BusinessRules, template: ExportTemplate) -> BusinessRules:
    """Return the business rules with the loader fields in the template's column order."""
    position = {name: index for index, name in enumerate(template.headers)}
    fields = sorted(business_rules.fields, key=lambda field: position[field.column])
    return business_rules.model_copy(update={"fields": fields})
