"""Change checks (CONTRACTS §6): the rules a change must pass before it is stored as pending.

Checked against the run's stored records and issues and the config versions the run started
with. Any failure raises ChangeRejectedError and nothing in the request is saved.
"""

from collections.abc import Sequence

from app.config.field_rules import FieldRule
from app.config.issue_catalogue import IssueCatalogue
from app.contracts.changes import (
    AcceptWarningChange,
    Change,
    ExcludeRecordChange,
    PickAlternativeChange,
    RestoreRecordChange,
    SetValueChange,
    UndoBulkChange,
)
from app.contracts.issue import Issue
from app.contracts.record import StoredRecord
from app.review.errors import ChangeRejectedError
from app.review.state import ReviewState, has_open_field_issue
from app.transform.lookup_matching import BOOLEAN_VALUES
from app.validation.service import ValidationConfig


def check_change(
    change: Change,
    state: ReviewState,
    earlier_changes: Sequence[Change],
    config: ValidationConfig,
) -> None:
    """Raise ChangeRejectedError if the change breaks a rule; `earlier_changes` are stored ones."""
    if isinstance(change, SetValueChange):
        check_set_value(change, state, config)
    elif isinstance(change, PickAlternativeChange):
        check_pick_alternative(change, state, config)
    elif isinstance(change, AcceptWarningChange):
        check_accept_warning(change, state, config.issue_catalogue)
    elif isinstance(change, ExcludeRecordChange):
        find_record(state, change.record_id)
        require_text(change.reason, "A reason is required to exclude a record. Add one.")
    elif isinstance(change, RestoreRecordChange):
        find_record(state, change.record_id)
    else:
        check_undo_bulk(change, earlier_changes)


def find_record(state: ReviewState, record_id: str) -> StoredRecord:
    """Return a record of the run, or reject the change."""
    record = state.records.get(record_id)
    if record is None:
        raise ChangeRejectedError(
            f"Record {record_id} is not in this run. Reload the run and try again."
        )
    return record


def find_editable_rule(config: ValidationConfig, field: str) -> FieldRule:
    """Return the rule of a field the user may change: an extracted field of the config."""
    for rule in config.field_rules.fields:
        if rule.key == field and rule.role == "extracted":
            return rule
    raise ChangeRejectedError(
        f"The field '{field}' cannot be changed in the tool. Choose another field."
    )


def require_text(text: str | None, message: str) -> None:
    """Reject the change with `message` when the text is missing or blank."""
    if text is None or not text.strip():
        raise ChangeRejectedError(message)


def check_set_value(change: SetValueChange, state: ReviewState, config: ValidationConfig) -> None:
    """Check a new value: list values from the run's lists; a reason when no issue is open."""
    find_record(state, change.record_id)
    rule = find_editable_rule(config, change.field)
    if change.value is not None and change.value.strip():
        check_list_value(rule, change.value, config)
    # A value without an open issue was not flagged, so changing it needs a reason
    if not has_open_field_issue(state, change.record_id, change.field):
        require_text(
            change.reason,
            f"{rule.column} has no open issue, so a reason is required to change it. "
            "Add a reason and save again.",
        )


def check_list_value(rule: FieldRule, value: str, config: ValidationConfig) -> None:
    """Reject a list or Y/N field value that is not one of the allowed values."""
    allowed: Sequence[str] | None = None
    if rule.lookup_sheet is not None:
        allowed = config.lookup_lists.sheets.get(rule.lookup_sheet, [])
    elif rule.type == "boolean":
        allowed = BOOLEAN_VALUES
    if allowed is not None and value not in allowed:
        raise ChangeRejectedError(
            f"'{value}' is not an allowed value for {rule.column}. Pick a value from the list."
        )


def check_pick_alternative(
    change: PickAlternativeChange, state: ReviewState, config: ValidationConfig
) -> None:
    """Check the field has an alternative with the chosen index."""
    record = find_record(state, change.record_id)
    rule = find_editable_rule(config, change.field)
    stored = record.fields.get(rule.key)
    extraction = stored.extraction if stored is not None else None
    if extraction is None or change.alternative_index >= len(extraction.alternatives):
        raise ChangeRejectedError(
            f"{rule.column} has no alternative number {change.alternative_index + 1}. "
            "Reload the record and choose again."
        )


def check_accept_warning(
    change: AcceptWarningChange, state: ReviewState, catalogue: IssueCatalogue
) -> None:
    """Check a warning can be accepted; individual-review ones one at a time, source viewed."""
    issue = find_issue(state, change.issue_id)
    if issue.severity != "warning":
        raise ChangeRejectedError("Only warnings can be accepted. Fix this issue instead.")
    if not issue.individual_review:
        return
    # Individual-review warnings: never in a bulk action, source opened, note when required
    if change.bulk_id is not None:
        raise ChangeRejectedError(
            "This warning must be reviewed on its own, so it cannot be part of a bulk action. "
            "Open its source and accept it by itself.",
            code="BULK_ACCEPT_NOT_ALLOWED",
        )
    if not change.source_viewed:
        raise ChangeRejectedError("Open the source before accepting this warning.")
    if is_note_required(issue, catalogue):
        require_text(change.note, "Add a note saying what you did, then accept this warning.")


def find_issue(state: ReviewState, issue_id: str) -> Issue:
    """Return an issue of the run that is not resolved, or reject the change."""
    issue = state.issues.get(issue_id)
    if issue is None or issue.status == "resolved":
        raise ChangeRejectedError(
            f"Issue {issue_id} is not open in this run. Reload the run and try again."
        )
    return issue


def is_note_required(issue: Issue, catalogue: IssueCatalogue) -> bool:
    """Return True if the catalogue says accepting this issue needs a note."""
    definitions = catalogue.record_issues if issue.record_id is not None else catalogue.run_issues
    definition = definitions.get(issue.code)
    return definition is not None and definition.note_required


def check_undo_bulk(change: UndoBulkChange, earlier_changes: Sequence[Change]) -> None:
    """Check the bulk action exists and has not been undone already."""
    bulk_ids = [c.bulk_id for c in earlier_changes if not isinstance(c, UndoBulkChange)]
    if change.bulk_id not in bulk_ids:
        raise ChangeRejectedError(
            f"There is no bulk action {change.bulk_id} in this run. Reload the run and try again."
        )
    undone_ids = [c.bulk_id for c in earlier_changes if isinstance(c, UndoBulkChange)]
    if change.bulk_id in undone_ids:
        raise ChangeRejectedError(f"Bulk action {change.bulk_id} was already undone.")
