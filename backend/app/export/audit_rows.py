"""Audit workbook rows (CONTRACTS §8): Summary, Values, Edits, Excluded and Run issues.

Built from the review database and the run store; `audit_workbook.py` writes them to Excel.
Lists inside one cell (several sources or issues) are written one per line.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from pydantic import BaseModel

from app.config.field_rules import FieldRule, FieldRules
from app.contracts.changes import (
    AcceptWarningChange,
    Change,
    ExcludeRecordChange,
    PickAlternativeChange,
    RestoreRecordChange,
    SetValueChange,
)
from app.contracts.chunk import Chunk
from app.contracts.export import (
    AuditEditRow,
    AuditExcludedRow,
    AuditRunIssueRow,
    AuditSummaryRow,
    AuditValueRow,
    ExportInfo,
)
from app.contracts.extraction import Evidence
from app.contracts.issue import Issue
from app.contracts.record import StoredField, StoredRecord
from app.contracts.run import RunInfo
from app.export.loader import find_export_text
from app.review.view import SourceLocation, SourceLocator, format_written
from app.storage.review_db import StoredChangeRow
from app.storage.run_store import DocumentInfo
from app.validation.duplicates import find_name_rule, read_name

# Several entries in one cell are written one per line
LINE_BREAK = "\n"

# Summary wording
DRAFT_LABEL = "Draft"
VERIFIED_LABEL = "Verified"
NOT_SET = "none"


@dataclass(frozen=True)
class AuditSource:
    """Everything the audit workbook is built from, for one export of one run."""

    run: RunInfo
    export: ExportInfo
    records: Sequence[StoredRecord]
    issues: Sequence[Issue]
    changes: Sequence[StoredChangeRow]
    documents: Sequence[DocumentInfo]
    chunks: Sequence[Chunk]
    field_rules: FieldRules
    models: Mapping[str, str]


class AuditRows(BaseModel):
    """The rows of each audit sheet."""

    summary: list[AuditSummaryRow]
    values: list[AuditValueRow]
    edits: list[AuditEditRow]
    excluded: list[AuditExcludedRow]
    run_issues: list[AuditRunIssueRow]


def build_audit_rows(source: AuditSource) -> AuditRows:
    """Build the rows of all five audit sheets."""
    locator = SourceLocator(source.chunks, source.documents)
    return AuditRows(
        summary=build_summary_rows(source),
        values=build_value_rows(source, locator),
        edits=build_edit_rows(source),
        excluded=build_excluded_rows(source, locator),
        run_issues=build_run_issue_rows(source.issues),
    )


# ----- Summary -----


def build_summary_rows(source: AuditSource) -> list[AuditSummaryRow]:
    """Return the Summary settings: run, export, verification, documents, versions, counts."""
    run, export = source.run, source.export
    entries: list[tuple[str, str]] = [
        ("Run name", run.name),
        ("Run ID", run.run_id),
        ("Export number", str(export.number)),
        ("Export type", DRAFT_LABEL if export.is_draft else VERIFIED_LABEL),
        ("Exported by", export.exported_by),
        ("Exported at", export.exported_at.isoformat()),
        ("Verified by", run.verified_by or NOT_SET),
        ("Verified at", run.verified_at.isoformat() if run.verified_at else NOT_SET),
    ]
    entries += [
        (f"Document {document.document_id}", f"{document.file_name} (SHA-256 {document.sha256})")
        for document in source.documents
    ]
    entries += build_version_entries(source)
    entries += build_count_entries(source.records, source.issues)
    return [AuditSummaryRow(label=label, value=value) for label, value in entries]


def build_version_entries(source: AuditSource) -> list[tuple[str, str]]:
    """Return the config versions the run used, its reference data version and the models."""
    versions = source.run.config_versions
    entries = [
        ("Field rules version", versions.field_rules),
        ("Issue catalogue version", versions.issue_catalogue),
        ("Lookup lists version", versions.lookup_lists),
        ("DFD template version", versions.dfd_template),
        ("Reference data mapping version", versions.reference_data_mapping),
        ("Reference data version", source.run.reference_data_version or NOT_SET),
    ]
    entries += [(f"Prompt {name} version", version) for name, version in versions.prompts.items()]
    entries += [(f"Model {node}", model) for node, model in source.models.items()]
    return entries


def build_count_entries(
    records: Sequence[StoredRecord], issues: Sequence[Issue]
) -> list[tuple[str, str]]:
    """Return the open issue counts by severity (excluded records left out)."""
    excluded_ids = {record.record_id for record in records if record.exclusion is not None}
    live = [i for i in issues if i.status == "open" and i.record_id not in excluded_ids]
    return [
        ("Open errors", str(sum(1 for issue in live if issue.severity == "error"))),
        ("Open warnings", str(sum(1 for issue in live if issue.severity == "warning"))),
        ("Open info", str(sum(1 for issue in live if issue.severity == "info"))),
    ]


# ----- Values -----


def build_value_rows(source: AuditSource, locator: SourceLocator) -> list[AuditValueRow]:
    """Return one row per included record and loader field, in loader column order."""
    name_rule = find_name_rule(source.field_rules)
    rows: list[AuditValueRow] = []
    for record in source.records:
        if record.exclusion is not None:
            continue
        own_issues = [issue for issue in source.issues if issue.record_id == record.record_id]
        for rule in source.field_rules.fields:
            # Record-level issues have no field; they are shown on the record name's row
            field_issues = [
                issue
                for issue in own_issues
                if issue.field == rule.key or (issue.field is None and rule.key == name_rule.key)
            ]
            rows.append(build_value_row(record, rule, name_rule, field_issues, locator))
    return rows


def build_value_row(
    record: StoredRecord,
    rule: FieldRule,
    name_rule: FieldRule,
    issues: Sequence[Issue],
    locator: SourceLocator,
) -> AuditValueRow:
    """Return one Values row: value as written, exported value, origin, sources, checks, issues."""
    stored = record.fields.get(rule.key)
    evidence = find_field_evidence(stored)
    locations = [locator.locate(pair.chunk_id) for pair in evidence]
    extraction = stored.extraction if stored is not None else None
    verification = stored.verification if stored is not None else None
    return AuditValueRow(
        record_id=record.record_id,
        consumable_type=read_name(record, name_rule),
        field=rule.column,
        written_value=find_written_text(rule, stored),
        exported_value=find_export_text(rule, record),
        origin=stored.output.origin if stored is not None else rule.role,
        source_document=join_lines(unique(loc.file_name for loc in locations if loc.file_name)),
        location=join_lines(format_location(location) for location in locations),
        source_quote=join_lines(pair.quote for pair in evidence),
        extraction_status=extraction.status if extraction is not None else None,
        citation_check=verification.citation_check if verification is not None else None,
        verification_verdict=verification.verdict if verification is not None else None,
        issue_codes=join_lines(issue.code for issue in issues),
        issue_outcome=join_lines(describe_outcome(issue) for issue in issues),
    )


def find_written_text(rule: FieldRule, stored: StoredField | None) -> str | None:
    """Return the value as written in the document; a conflict's alternatives are all listed.

    Several values (a list, or the alternatives) are joined with the field's separator, as for
    multi-value fields. A field that was not found or not extracted gives None (an empty cell).
    """
    if stored is None or stored.extraction is None:
        return None
    extraction = stored.extraction
    if extraction.value is not None:
        return format_written(rule, extraction.value)
    # A conflicting field has no single value: every alternative as written is listed
    texts = [
        format_written(rule, alternative.value) or "" for alternative in extraction.alternatives
    ]
    return format_written(rule, texts) if texts else None


def find_field_evidence(stored: StoredField | None) -> list[Evidence]:
    """Return a field's evidence: found evidence, or the picked (or every) alternative's."""
    if stored is None or stored.extraction is None:
        return []
    extraction = stored.extraction
    if extraction.evidence:
        return list(extraction.evidence)
    index = stored.output.selected_alternative
    if index is not None and index < len(extraction.alternatives):
        return list(extraction.alternatives[index].evidence)
    return [pair for alternative in extraction.alternatives for pair in alternative.evidence]


def format_location(location: SourceLocation) -> str:
    """Return a location as text: document, section, page or sheet and rows."""
    parts = [location.file_name or location.chunk_id]
    if location.section:
        parts.append(location.section)
    if location.page is not None:
        parts.append(f"page {location.page}")
    if location.sheet:
        parts.append(f"sheet {location.sheet}")
    if location.row_range:
        parts.append(f"rows {location.row_range}")
    return ", ".join(parts)


def describe_outcome(issue: Issue) -> str:
    """Return an issue's outcome: open, or accepted or resolved (and by whom)."""
    if issue.status == "open" or issue.closed_by is None:
        return issue.status
    return f"{issue.status} by {issue.closed_by}"


def unique(values: Iterable[str]) -> list[str]:
    """Return the values without repeats, in first-seen order."""
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def join_lines(values: Iterable[str]) -> str | None:
    """Join texts one per line; nothing to join gives None (an empty cell)."""
    texts = list(values)
    return LINE_BREAK.join(texts) if texts else None


# ----- Edits -----


def build_edit_rows(source: AuditSource) -> list[AuditEditRow]:
    """Return one row per applied change, in the order the changes were saved."""
    name_rule = find_name_rule(source.field_rules)
    names = {record.record_id: read_name(record, name_rule) for record in source.records}
    columns = {rule.key: rule.column for rule in source.field_rules.fields}
    issues_by_id = {issue.issue_id: issue for issue in source.issues}
    rows: list[AuditEditRow] = []
    for row in source.changes:
        if row.stored.status != "applied":
            continue
        change = row.stored.change
        record_id, field, reason = describe_change(change, issues_by_id)
        rows.append(
            AuditEditRow(
                change_id=change.change_id,
                record_id=record_id,
                consumable_type=names.get(record_id) if record_id is not None else None,
                field=columns.get(field, field) if field is not None else None,
                type=change.type,
                old_value=row.old_value,
                new_value=row.new_value,
                reason=reason,
                user=row.stored.user,
                time=row.stored.timestamp,
                bulk_id=change.bulk_id,
            )
        )
    return rows


def describe_change(
    change: Change, issues_by_id: Mapping[str, Issue]
) -> tuple[str | None, str | None, str | None]:
    """Return a change's record ID, field key and reason (or note), where it has them."""
    if isinstance(change, SetValueChange):
        return change.record_id, change.field, change.reason
    if isinstance(change, PickAlternativeChange):
        return change.record_id, change.field, None
    # An accepted warning is shown on the record and field of its issue
    if isinstance(change, AcceptWarningChange):
        issue = issues_by_id.get(change.issue_id)
        if issue is None:
            return None, None, change.note
        return issue.record_id, issue.field, change.note
    if isinstance(change, ExcludeRecordChange):
        return change.record_id, None, change.reason
    if isinstance(change, RestoreRecordChange):
        return change.record_id, None, None
    return None, None, None


# ----- Excluded and run issues -----


def build_excluded_rows(source: AuditSource, locator: SourceLocator) -> list[AuditExcludedRow]:
    """Return one row per excluded record: name, where it was found, who excluded it and why."""
    name_rule = find_name_rule(source.field_rules)
    rows: list[AuditExcludedRow] = []
    for record in source.records:
        if record.exclusion is None:
            continue
        found_in = [format_location(locator.locate(chunk_id)) for chunk_id in record.found_in]
        rows.append(
            AuditExcludedRow(
                record_id=record.record_id,
                name=read_name(record, name_rule),
                found_in=join_lines(found_in) or "",
                excluded_by=record.exclusion.by,
                excluded_at=record.exclusion.at,
                reason=record.exclusion.reason,
            )
        )
    return rows


def build_run_issue_rows(issues: Sequence[Issue]) -> list[AuditRunIssueRow]:
    """Return the run-level issues that are not resolved."""
    return [
        AuditRunIssueRow(code=issue.code, message=issue.message)
        for issue in issues
        if issue.record_id is None and issue.status != "resolved"
    ]
