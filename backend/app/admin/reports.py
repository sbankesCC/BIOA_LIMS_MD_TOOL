"""Upload check findings shared by the admin uploads (lookup lists and reference data).

A problem blocks the upload; a warning is reported and the upload can still be applied.
"""

from typing import Literal

from pydantic import BaseModel

FindingSeverity = Literal["problem", "warning"]


class UploadFinding(BaseModel):
    """One check finding: where it is (sheet, row) and a plain explanation of what to do."""

    severity: FindingSeverity
    code: str
    sheet: str | None = None
    row: int | None = None
    message: str


def make_problem(
    code: str, message: str, sheet: str | None = None, row: int | None = None
) -> UploadFinding:
    """Build a finding that blocks the upload."""
    return UploadFinding(severity="problem", code=code, sheet=sheet, row=row, message=message)


def make_warning(
    code: str, message: str, sheet: str | None = None, row: int | None = None
) -> UploadFinding:
    """Build a finding that is reported but does not block the upload."""
    return UploadFinding(severity="warning", code=code, sheet=sheet, row=row, message=message)
