"""Bulk preview (CONTRACTS §13 `bulk-preview`): the records a bulk action would touch (UI_SPEC).

Four modes: change all (same issue code, field and value), fill missing (same field, no value),
accept all of a type (same warning code, any field) and resolve repeated conflicts (same field,
same set of alternatives). Excluded records never match. Read only: nothing is changed here.
Individual-review issues are never offered for bulk actions (§6).
"""

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel

from app.config.field_rules import FieldRule, FieldRules
from app.contracts.extraction import Alternative, ExtractedValue
from app.contracts.issue import Issue
from app.contracts.record import StoredRecord
from app.review.errors import ReviewError
from app.validation.duplicates import find_name_rule, read_name

BulkMode = Literal["change_all", "fill_missing", "accept_type", "resolve_conflicts"]

# An alternative's value in a form that can go in a set (a list value becomes a tuple)
AlternativeKey = str | tuple[str, ...]


class BulkRequest(BaseModel):
    """What the user selected: the mode, and the issue, field or alternative it starts from.

    `change_all`, `accept_type` and `resolve_conflicts` start from `issue_id`; `fill_missing`
    from `field`; `resolve_conflicts` also needs `alternative_index` (in the issue's record).
    """

    mode: BulkMode
    issue_id: str | None = None
    field: str | None = None
    alternative_index: int | None = None


class BulkPreviewMatch(BaseModel):
    """One record a bulk action would touch, with its matching issue and current value.

    `alternative_index` (resolve conflicts only) is the chosen value's index in this record's
    own alternatives list.
    """

    record_id: str
    name: str | None
    issue_id: str | None
    value: str | None
    alternative_index: int | None = None


class BulkPreview(BaseModel):
    """The selection (mode, issue, code, field, its current value) and every matching record."""

    mode: BulkMode
    issue_id: str | None
    code: str | None
    field: str | None
    value: str | None
    count: int
    matches: list[BulkPreviewMatch]


class BulkScope:
    """The run's records (all, by ID) and issues, plus the record name rule."""

    def __init__(
        self, records: Sequence[StoredRecord], issues: Sequence[Issue], field_rules: FieldRules
    ) -> None:
        """Index the records by ID and keep the issues and field rules."""
        self.records = list(records)
        self.by_id = {record.record_id: record for record in records}
        self.issues = list(issues)
        self.field_rules = field_rules
        self.name_rule = find_name_rule(field_rules)

    def find_included(self, record_id: str | None) -> StoredRecord | None:
        """Return a record that is not excluded, or None."""
        record = self.by_id.get(record_id or "")
        return record if record is not None and record.exclusion is None else None

    def make_match(
        self, record: StoredRecord, issue_id: str | None, field: str | None, index: int | None
    ) -> BulkPreviewMatch:
        """Return one match: the record's ID, name, issue, current value and alternative."""
        return BulkPreviewMatch(
            record_id=record.record_id,
            name=read_name(record, self.name_rule),
            issue_id=issue_id,
            value=read_output_value(record, field),
            alternative_index=index,
        )


def find_bulk_matches(
    records: Sequence[StoredRecord],
    issues: Sequence[Issue],
    request: BulkRequest,
    field_rules: FieldRules,
) -> BulkPreview:
    """Return the records the selected bulk action would touch."""
    scope = BulkScope(records, issues, field_rules)
    if request.mode == "fill_missing":
        return preview_fill_missing(scope, require_field(request))
    issue = find_bulk_issue(issues, require_issue_id(request))
    if request.mode == "change_all":
        return preview_change_all(scope, require_field_issue(issue))
    if request.mode == "accept_type":
        return preview_accept_type(scope, require_warning(issue))
    return preview_resolve_conflicts(
        scope, require_field_issue(issue), require_alternative_index(request)
    )


# ----- Modes -----


def preview_change_all(scope: BulkScope, issue: Issue) -> BulkPreview:
    """Match open issues of the same code on the same field, holding the same current value."""
    field = issue.field
    value = read_output_value(scope.by_id.get(issue.record_id or ""), field)
    matches: list[BulkPreviewMatch] = []
    for other in find_open_issues(scope, issue.code, field):
        record = scope.find_included(other.record_id)
        if record is not None and read_output_value(record, field) == value:
            matches.append(scope.make_match(record, other.issue_id, field, None))
    return make_preview("change_all", issue, value, matches)


def preview_fill_missing(scope: BulkScope, field: str) -> BulkPreview:
    """Match included records whose field has no value (a conflict is resolved, not filled)."""
    rule = find_fillable_rule(scope.field_rules, field)
    matches: list[BulkPreviewMatch] = []
    for record in scope.records:
        if record.exclusion is not None or not is_missing(record, rule.key):
            continue
        issue_id = find_open_field_issue_id(scope, record.record_id, rule.key)
        matches.append(scope.make_match(record, issue_id, rule.key, None))
    return BulkPreview(
        mode="fill_missing",
        issue_id=None,
        code=None,
        field=rule.key,
        value=None,
        count=len(matches),
        matches=matches,
    )


def preview_accept_type(scope: BulkScope, issue: Issue) -> BulkPreview:
    """Match open warnings of the same code on any field of included records."""
    matches: list[BulkPreviewMatch] = []
    for other in scope.issues:
        record = scope.find_included(other.record_id)
        # Same code, still open, a warning that may be accepted in bulk
        if record is None or other.code != issue.code or other.status != "open":
            continue
        if other.severity != "warning" or other.individual_review:
            continue
        matches.append(scope.make_match(record, other.issue_id, other.field, None))
    value = read_output_value(scope.by_id.get(issue.record_id or ""), issue.field)
    return make_preview("accept_type", issue, value, matches)


def preview_resolve_conflicts(scope: BulkScope, issue: Issue, index: int) -> BulkPreview:
    """Match open conflicts on the same field with the same set of alternatives, in any order.

    Each match gives the index of the chosen alternative in its own record's list.
    """
    field = issue.field
    selected = scope.by_id.get(issue.record_id or "")
    chosen = find_chosen_alternative(read_alternative_keys(selected, field), index, issue)
    wanted = set(read_alternative_keys(selected, field))
    matches: list[BulkPreviewMatch] = []
    for other in find_open_issues(scope, issue.code, field):
        record = scope.find_included(other.record_id)
        keys = read_alternative_keys(record, field)
        if record is not None and set(keys) == wanted:
            matches.append(scope.make_match(record, other.issue_id, field, keys.index(chosen)))
    value = read_output_value(selected, field)
    return make_preview("resolve_conflicts", issue, value, matches)


def make_preview(
    mode: BulkMode, issue: Issue, value: str | None, matches: list[BulkPreviewMatch]
) -> BulkPreview:
    """Return a preview that started from an issue."""
    return BulkPreview(
        mode=mode,
        issue_id=issue.issue_id,
        code=issue.code,
        field=issue.field,
        value=value,
        count=len(matches),
        matches=matches,
    )


# ----- Request checks -----


def require_issue_id(request: BulkRequest) -> str:
    """Return the request's issue ID; this mode starts from an issue."""
    if request.issue_id is None:
        raise ReviewError(
            "BULK_NOT_POSSIBLE",
            f"A {request.mode} preview starts from an issue. Send the issue_id of the selected "
            "issue.",
        )
    return request.issue_id


def require_field(request: BulkRequest) -> str:
    """Return the request's field key; fill missing starts from a field."""
    if request.field is None:
        raise ReviewError(
            "BULK_NOT_POSSIBLE", "A fill_missing preview starts from a field. Send its field key."
        )
    return request.field


def require_alternative_index(request: BulkRequest) -> int:
    """Return the chosen alternative's index; resolving conflicts needs it."""
    if request.alternative_index is None:
        raise ReviewError(
            "BULK_NOT_POSSIBLE",
            "A resolve_conflicts preview needs the chosen alternative. Send its alternative_index.",
        )
    return request.alternative_index


def find_bulk_issue(issues: Sequence[Issue], issue_id: str) -> Issue:
    """Return the selected issue if a bulk action can start from it; raise ReviewError if not."""
    issue = next((issue for issue in issues if issue.issue_id == issue_id), None)
    if issue is None:
        raise ReviewError(
            "ISSUE_NOT_FOUND", f"Issue {issue_id} was not found in this run. Reload the run."
        )
    # Run-level issues belong to no record, so no other record can share them
    if issue.record_id is None:
        raise ReviewError(
            "BULK_NOT_POSSIBLE",
            f"Issue {issue_id} is about the whole run, so it cannot be applied to records. "
            "Resolve it on its own.",
        )
    if issue.individual_review:
        raise ReviewError(
            "BULK_ACCEPT_NOT_ALLOWED",
            f"Issue {issue_id} must be reviewed one record at a time. Open its source and "
            "resolve it on its own record.",
        )
    return issue


def require_field_issue(issue: Issue) -> Issue:
    """Return the issue if it is on a field; record-level issues have no value to compare."""
    if issue.field is None:
        raise ReviewError(
            "BULK_NOT_POSSIBLE",
            f"Issue {issue.issue_id} is not on a field, so it cannot be applied to other "
            "records. Resolve it on its own record.",
        )
    return issue


def require_warning(issue: Issue) -> Issue:
    """Return the issue if it is a warning; only warnings can be accepted."""
    if issue.severity != "warning":
        raise ReviewError(
            "BULK_NOT_POSSIBLE",
            f"Issue {issue.issue_id} is not a warning, so it cannot be accepted. Fix the value "
            "instead.",
        )
    return issue


def find_fillable_rule(field_rules: FieldRules, field: str) -> FieldRule:
    """Return the rule of a field the user can fill; only extracted fields can be changed."""
    rule = next((rule for rule in field_rules.fields if rule.key == field), None)
    if rule is None or rule.role != "extracted":
        raise ReviewError(
            "BULK_NOT_POSSIBLE",
            f"'{field}' is not a field the review can fill. Pick a field from the review view.",
        )
    return rule


def find_chosen_alternative(keys: list[AlternativeKey], index: int, issue: Issue) -> AlternativeKey:
    """Return the chosen alternative of the selected conflict; the index must be in its list."""
    if not keys:
        raise ReviewError(
            "BULK_NOT_POSSIBLE",
            f"Issue {issue.issue_id} is not on a conflicting value, so there is no alternative "
            "to pick. Use another action.",
        )
    if index >= len(keys):
        raise ReviewError(
            "BULK_NOT_POSSIBLE",
            f"The conflict of issue {issue.issue_id} has {len(keys)} alternatives, so there is "
            f"no alternative {index}. Pick one of them.",
        )
    return keys[index]


# ----- Record reading -----


def find_open_issues(scope: BulkScope, code: str, field: str | None) -> list[Issue]:
    """Return the open issues with one code on one field."""
    return [
        issue
        for issue in scope.issues
        if issue.status == "open" and issue.code == code and issue.field == field
    ]


def find_open_field_issue_id(scope: BulkScope, record_id: str, field: str) -> str | None:
    """Return the ID of a field's first open issue on one record (the one a fill answers)."""
    for issue in scope.issues:
        if issue.record_id == record_id and issue.field == field and issue.status == "open":
            return issue.issue_id
    return None


def read_output_value(record: StoredRecord | None, field: str | None) -> str | None:
    """Return a record's current output value for one field (None if missing)."""
    if record is None or field is None or field not in record.fields:
        return None
    return record.fields[field].output.value


def is_missing(record: StoredRecord, field: str) -> bool:
    """Return True if the field has no value and is not an unresolved conflict."""
    stored = record.fields.get(field)
    if stored is None:
        return False
    if stored.extraction is not None and stored.extraction.status == "conflicting":
        return False
    value = stored.output.value
    return value is None or not value.strip()


def read_alternative_keys(record: StoredRecord | None, field: str | None) -> list[AlternativeKey]:
    """Return a conflicting field's alternatives as set keys, in the record's order."""
    if record is None or field is None or field not in record.fields:
        return []
    extraction = record.fields[field].extraction
    if extraction is None or extraction.status != "conflicting":
        return []
    return [make_alternative_key(alternative) for alternative in extraction.alternatives]


def make_alternative_key(alternative: Alternative) -> AlternativeKey:
    """Return an alternative's value as written; a list value becomes a tuple."""
    value: ExtractedValue = alternative.value
    return value if isinstance(value, str) else tuple(value)
