"""Eval case (CONTRACTS §9): `case.yaml`, the expected extraction and the seeded errors of a case.

Expected sources name a document and page or section, never chunk IDs. A field key missing from
a record's expected fields is "not labeled", not wrong. Field keys come from `field_rules.yaml`.
"""

from typing import Literal

from app.contracts.base import ContractModel
from app.contracts.extraction import ExtractedValue, FieldStatus
from app.contracts.verification import FieldVerdict

CaseSource = Literal["synthetic", "bioa"]


class EvalCaseInfo(ContractModel):
    """One eval case: where its documents come from, who labeled it, and against which rules."""

    id: str
    description: str
    source: CaseSource
    tags: list[str] = []
    labeled_by: str
    labeled_on: str
    field_rules_version: str


class ExpectedSource(ContractModel):
    """Where a record is expected: a document file name, plus a page or a section (or sheet)."""

    document: str
    page: int | None = None
    section: str | None = None


class ExpectedField(ContractModel):
    """The labeled status of one field, with its value (found) or its alternatives (conflicting)."""

    status: FieldStatus
    value: ExtractedValue | None = None
    alternatives: list[ExtractedValue] = []


class ExpectedRecord(ContractModel):
    """One expected record; `name` is read from the record name field's key in the file."""

    name: str
    found_in: list[ExpectedSource] = []
    serial_dilution_level: bool | None = None
    fields: dict[str, ExpectedField] = {}


class ExpectedExtraction(ContractModel):
    """The whole `expected_extraction.json`: expected records and excluded item names."""

    records: list[ExpectedRecord]
    excluded_items: list[str] = []


class SeededError(ContractModel):
    """A mistake planted into the extraction, and the verdict verification should give it."""

    record: str
    field: str
    planted_value: ExtractedValue
    expected_verdict: FieldVerdict


class SeededErrors(ContractModel):
    """The whole `seeded_errors.json` (optional in a case)."""

    notes: str = ""
    errors: list[SeededError] = []
