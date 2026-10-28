"""DFD template (`dfd_template.xlsx`): the loader layout, `Sheet1` with one header row."""

import hashlib
from pathlib import Path

from openpyxl import load_workbook
from pydantic import BaseModel

from app.config.errors import ConfigError, require_file

FILE_NAME = "dfd_template.xlsx"
SHEET_NAME = "Sheet1"

# The template has no version inside it, so its version is a short content fingerprint
FINGERPRINT_LENGTH = 12


class DfdTemplate(BaseModel):
    """The loader template: where it is, its column headers and a content fingerprint."""

    path: Path
    headers: list[str]
    version: str


def load_dfd_template(path: Path) -> DfdTemplate:
    """Load the template and check it has only `Sheet1` with a single header row."""
    require_file(path)
    workbook = load_workbook(path, data_only=True)
    if SHEET_NAME not in workbook.sheetnames:
        raise ConfigError([f"{FILE_NAME}: the sheet '{SHEET_NAME}' is missing."])
    rows = [row for row in workbook[SHEET_NAME].iter_rows(values_only=True) if any(row)]
    problems: list[str] = []
    # Row 1 holds the headers and nothing else may be filled in
    if len(rows) != 1:
        problems.append(f"{FILE_NAME}: '{SHEET_NAME}' must have only the header row.")
    headers = [cell for cell in rows[0] if cell is not None] if rows else []
    if not headers or not all(isinstance(cell, str) for cell in headers):
        problems.append(f"{FILE_NAME}: row 1 of '{SHEET_NAME}' must hold text column names.")
    if problems:
        raise ConfigError(problems)
    return DfdTemplate(
        path=path, headers=[str(cell) for cell in headers], version=fingerprint(path)
    )


def fingerprint(path: Path) -> str:
    """Return a short SHA-256 of a file, used as the version of a file with no version inside."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{digest[:FINGERPRINT_LENGTH]}"
