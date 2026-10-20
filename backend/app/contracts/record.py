"""Stored record (CONTRACTS §4): one record with a section per layer, for every loader field.

Each layer writes only its own section. Field keys come from `field_rules.yaml`, so the check
that a record holds every field (all 22 today) takes the field rules as input.
"""

from datetime import datetime
from typing import Literal

from app.config.field_rules import FieldRules
from app.contracts.base import ContractModel
from app.contracts.extraction import ExtractedField
from app.contracts.verification import CitationCheck, FieldVerdict, RecordFinding

Origin = Literal["extracted", "default", "fixed", "user_edited", "blank_for_now", "system"]
ActionNeeded = Literal["fix", "check", "none", "excluded"]


class RecordExtraction(ContractModel):
    """Record-level extraction section, wrapped by code from the extraction response."""

    record_ref: str
    record_summary: str
    record_warning: str | None = None


class RecordVerification(ContractModel):
    """Record-level verification section: record findings and whether it was re-extracted."""

    findings: list[RecordFinding] = []
    re_extracted: bool = False


class Exclusion(ContractModel):
    """Who excluded a record, when, and why."""

    by: str
    at: datetime
    reason: str


class FieldVerification(ContractModel):
    """Field-level verification: the code citation check and the agent's verdict, if any."""

    citation_check: CitationCheck | None = None
    verdict: FieldVerdict | None = None
    note: str | None = None


class FieldOutput(ContractModel):
    """Field-level output: the loader value (always text or empty), its origin and clean-ups."""

    value: str | None = None
    origin: Origin
    changes: list[str] = []
    selected_alternative: int | None = None


class StoredField(ContractModel):
    """One field of a stored record; `extraction` and `verification` are null if not extracted."""

    extraction: ExtractedField | None = None
    verification: FieldVerification | None = None
    output: FieldOutput
    issue_ids: list[str] = []


class StoredRecord(ContractModel):
    """A stored record with its sections and one entry per loader field."""

    record_id: str
    found_in: list[str]
    extraction: RecordExtraction
    verification: RecordVerification = RecordVerification()
    exclusion: Exclusion | None = None
    fields: dict[str, StoredField]
    issue_ids: list[str] = []
    action_needed: ActionNeeded = "none"


def find_record_field_problems(record: StoredRecord, field_rules: FieldRules) -> list[str]:
    """Return a problem for each loader field missing from the record and each unknown key."""
    expected_keys = [field.key for field in field_rules.fields]
    problems: list[str] = []
    # Every loader field must be present, whatever its role
    for key in expected_keys:
        if key not in record.fields:
            problems.append(f"Record {record.record_id} has no entry for field '{key}'.")
    # Keys the field rules do not define would never be exported
    for key in record.fields:
        if key not in expected_keys:
            problems.append(f"Record {record.record_id} has unknown field '{key}'.")
    return problems
