"""Exports and the audit workbook (CONTRACTS §7 `exports`, §8): export info and sheet rows."""

from datetime import datetime

from app.contracts.base import ContractModel


class ExportInfo(ContractModel):
    """One export of a run: its number, draft or verified, and its two files."""

    export_id: str
    number: int
    is_draft: bool
    loader_file: str
    audit_file: str
    exported_at: datetime
    exported_by: str


class AuditSummaryRow(ContractModel):
    """Summary sheet: one setting as a label and value."""

    label: str
    value: str


class AuditValueRow(ContractModel):
    """Values sheet: one record and field, with its exported value and where it came from."""

    record_id: str
    consumable_type: str | None
    field: str
    written_value: str | None
    exported_value: str | None
    origin: str
    source_document: str | None
    location: str | None
    source_quote: str | None
    extraction_status: str | None
    citation_check: str | None
    verification_verdict: str | None
    issue_codes: str | None
    issue_outcome: str | None


class AuditEditRow(ContractModel):
    """Edits sheet: one applied change with old and new value."""

    change_id: str
    record_id: str | None
    consumable_type: str | None
    field: str | None
    type: str
    old_value: str | None
    new_value: str | None
    reason: str | None
    user: str
    time: datetime
    bulk_id: str | None


class AuditExcludedRow(ContractModel):
    """Excluded sheet: one excluded record."""

    record_id: str
    name: str | None
    found_in: str
    excluded_by: str
    excluded_at: datetime
    reason: str


class AuditRunIssueRow(ContractModel):
    """Run issues sheet: one run-level issue."""

    code: str
    message: str
