"""Bulk preview (CONTRACTS §13 `bulk-preview`): the records a "Change all" would touch.

A match is an included record with an open issue of the same code on the same field, holding
the same current value. Individual-review issues are never offered for bulk actions (§6).
"""

from collections.abc import Sequence

from pydantic import BaseModel

from app.config.field_rules import FieldRules
from app.contracts.issue import Issue
from app.contracts.record import StoredRecord
from app.review.errors import ReviewError
from app.validation.duplicates import find_name_rule, read_name


class BulkPreviewMatch(BaseModel):
    """One record a bulk action would touch, with its matching issue."""

    record_id: str
    name: str | None
    issue_id: str


class BulkPreview(BaseModel):
    """The selected issue's code, field and value, and every matching record (itself included)."""

    issue_id: str
    code: str
    field: str
    value: str | None
    matches: list[BulkPreviewMatch]


def find_bulk_matches(
    records: Sequence[StoredRecord],
    issues: Sequence[Issue],
    issue_id: str,
    field_rules: FieldRules,
) -> BulkPreview:
    """Return the records matching an issue's field, code and current value."""
    issue = find_bulk_issue(issues, issue_id)
    field = issue.field or ""
    by_id = {record.record_id: record for record in records}
    value = read_output_value(by_id.get(issue.record_id or ""), field)
    name_rule = find_name_rule(field_rules)
    matches: list[BulkPreviewMatch] = []
    for other in issues:
        record = by_id.get(other.record_id or "")
        # Same open problem on the same field of an included record, with the same value
        if record is None or record.exclusion is not None or other.status != "open":
            continue
        if other.code != issue.code or other.field != field:
            continue
        if read_output_value(record, field) != value:
            continue
        name = read_name(record, name_rule)
        matches.append(
            BulkPreviewMatch(record_id=record.record_id, name=name, issue_id=other.issue_id)
        )
    return BulkPreview(
        issue_id=issue.issue_id, code=issue.code, field=field, value=value, matches=matches
    )


def find_bulk_issue(issues: Sequence[Issue], issue_id: str) -> Issue:
    """Return the selected issue if a bulk action can start from it; raise ReviewError if not."""
    issue = next((issue for issue in issues if issue.issue_id == issue_id), None)
    if issue is None:
        raise ReviewError(
            "ISSUE_NOT_FOUND", f"Issue {issue_id} was not found in this run. Reload the run."
        )
    # Run-level and record-level issues have no field value to compare
    if issue.record_id is None or issue.field is None:
        raise ReviewError(
            "BULK_NOT_POSSIBLE",
            f"Issue {issue_id} is not on a field, so it cannot be applied to other records. "
            "Resolve it on its own record.",
        )
    if issue.individual_review:
        raise ReviewError(
            "BULK_ACCEPT_NOT_ALLOWED",
            f"Issue {issue_id} must be reviewed one record at a time. Open its source and "
            "resolve it on its own record.",
        )
    return issue


def read_output_value(record: StoredRecord | None, field: str) -> str | None:
    """Return a record's current output value for one field (None if missing)."""
    if record is None or field not in record.fields:
        return None
    return record.fields[field].output.value
