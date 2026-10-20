"""Apply changes: turn pending changes into new output values, accepted warnings and exclusions.

Changes write only the user-owned parts of a record: a field's `output` and the record's
`exclusion`; accepting a warning sets the issue's status. Each change keeps what it replaced
(`before_state`) and what it wrote (`after_state`), so a bulk action can be undone.
"""

from collections.abc import Sequence
from datetime import datetime

from pydantic import BaseModel, JsonValue

from app.config.field_rules import FieldRule
from app.contracts.changes import (
    AcceptWarningChange,
    ExcludeRecordChange,
    PickAlternativeChange,
    RestoreRecordChange,
    SetValueChange,
    UndoBulkChange,
)
from app.contracts.issue import IssueHistoryEntry
from app.contracts.record import Exclusion, FieldOutput
from app.contracts.run import AuditEvent
from app.review.state import ReviewState
from app.storage.review_db import AppliedChange, StoredChangeRow
from app.transform.transform import transform_value
from app.validation.service import ValidationConfig

# Audit events written by the review service
RECORD_EXCLUDED = "record_excluded"
RECORD_RESTORED = "record_restored"
BULK_UNDONE = "bulk_undone"

# Issue history notes for steps that have no note of their own
ACCEPTANCE_UNDONE_NOTE = "acceptance undone"


class ApplyOutcome(BaseModel):
    """What applying one change did: the applied row data, audit events, history, undone IDs."""

    applied: AppliedChange
    events: list[AuditEvent] = []
    history: list[IssueHistoryEntry] = []
    undone_change_ids: list[str] = []


def apply_change(
    state: ReviewState,
    row: StoredChangeRow,
    rows: Sequence[StoredChangeRow],
    run_id: str,
    config: ValidationConfig,
    at: datetime,
) -> ApplyOutcome:
    """Apply one pending change to the state; `rows` are all the run's changes (for undo)."""
    change = row.stored.change
    if isinstance(change, SetValueChange):
        return apply_set_value(state, change, at)
    if isinstance(change, PickAlternativeChange):
        return apply_pick_alternative(state, change, config, at)
    if isinstance(change, AcceptWarningChange):
        return apply_accept_warning(state, change, row.stored.user, at)
    if isinstance(change, ExcludeRecordChange | RestoreRecordChange):
        return apply_exclusion(state, change, row, run_id, at)
    return apply_undo_bulk(state, change, row.stored.user, rows, run_id, at)


def apply_set_value(state: ReviewState, change: SetValueChange, at: datetime) -> ApplyOutcome:
    """Set a field's value as typed; old notes are dropped, as they described the old value."""
    value = change.value if change.value is not None and change.value.strip() else None
    output = FieldOutput(value=value, origin="user_edited")
    return replace_output(state, change.change_id, change.record_id, change.field, output, at)


def apply_pick_alternative(
    state: ReviewState, change: PickAlternativeChange, config: ValidationConfig, at: datetime
) -> ApplyOutcome:
    """Use one alternative as written, formatted by transformation like any extracted value."""
    stored = state.records[change.record_id].fields[change.field]
    alternatives = stored.extraction.alternatives if stored.extraction is not None else []
    rule = find_rule(config, change.field)
    alternative = alternatives[change.alternative_index]
    transformed = transform_value(rule, alternative.value, config.lookup_lists)
    output = FieldOutput(
        value=transformed.value,
        origin="user_edited",
        changes=transformed.changes,
        selected_alternative=change.alternative_index,
    )
    return replace_output(state, change.change_id, change.record_id, change.field, output, at)


def find_rule(config: ValidationConfig, field: str) -> FieldRule:
    """Return a field's rule from the run's config."""
    return next(rule for rule in config.field_rules.fields if rule.key == field)


def replace_output(
    state: ReviewState,
    change_id: str,
    record_id: str,
    field: str,
    output: FieldOutput,
    at: datetime,
) -> ApplyOutcome:
    """Write a field's new output section and remember the old one."""
    record = state.records[record_id]
    stored = record.fields[field]
    fields = {**record.fields, field: stored.model_copy(update={"output": output})}
    state.records[record_id] = record.model_copy(update={"fields": fields})
    applied = AppliedChange(
        change_id=change_id,
        applied_at=at,
        old_value=stored.output.value,
        new_value=output.value,
        before_state={"output": stored.output.model_dump(mode="json")},
        after_state={"output": output.model_dump(mode="json")},
    )
    return ApplyOutcome(applied=applied)


def apply_accept_warning(
    state: ReviewState, change: AcceptWarningChange, user: str, at: datetime
) -> ApplyOutcome:
    """Accept an open warning; one resolved since the change was saved is left alone."""
    applied = AppliedChange(change_id=change.change_id, applied_at=at)
    issue = state.issues.get(change.issue_id)
    if issue is None or issue.status != "open":
        return ApplyOutcome(applied=applied)
    accepted = issue.model_copy(update={"status": "accepted", "closed_by": user})
    state.issues[issue.issue_id] = accepted
    applied.before_state = read_issue_state(issue.status, issue.closed_by)
    applied.after_state = read_issue_state(accepted.status, accepted.closed_by)
    history = IssueHistoryEntry(
        issue_id=issue.issue_id, action="accepted", by=user, at=at, note=change.note
    )
    return ApplyOutcome(applied=applied, history=[history])


def read_issue_state(status: str, closed_by: str | None) -> JsonValue:
    """Return the part of an issue that accepting changes, as JSON."""
    return {"status": status, "closed_by": closed_by}


def apply_exclusion(
    state: ReviewState,
    change: ExcludeRecordChange | RestoreRecordChange,
    row: StoredChangeRow,
    run_id: str,
    at: datetime,
) -> ApplyOutcome:
    """Exclude a record (who, when, why) or restore it, with an audit event."""
    record = state.records[change.record_id]
    exclusion: Exclusion | None = None
    event_name = RECORD_RESTORED
    details: dict[str, JsonValue] = {"record_id": record.record_id, "change_id": change.change_id}
    if isinstance(change, ExcludeRecordChange):
        exclusion = Exclusion(by=row.stored.user, at=row.stored.timestamp, reason=change.reason)
        event_name = RECORD_EXCLUDED
        details["reason"] = change.reason
    state.records[record.record_id] = record.model_copy(update={"exclusion": exclusion})
    applied = AppliedChange(
        change_id=change.change_id,
        applied_at=at,
        before_state={"exclusion": dump_exclusion(record.exclusion)},
        after_state={"exclusion": dump_exclusion(exclusion)},
    )
    event = AuditEvent(event=event_name, run_id=run_id, by=row.stored.user, at=at, details=details)
    return ApplyOutcome(applied=applied, events=[event])


def dump_exclusion(exclusion: Exclusion | None) -> JsonValue:
    """Return an exclusion as JSON, or None."""
    return exclusion.model_dump(mode="json") if exclusion is not None else None


def apply_undo_bulk(
    state: ReviewState,
    change: UndoBulkChange,
    user: str,
    rows: Sequence[StoredChangeRow],
    run_id: str,
    at: datetime,
) -> ApplyOutcome:
    """Undo every applied change of a bulk action, newest first.

    A change whose target was changed again later is left as it is (the later change wins).
    """
    targets = [
        row
        for row in rows
        if row.stored.status == "applied"
        and row.undone_by is None
        and row.stored.change.type != "undo_bulk"
        and row.stored.change.bulk_id == change.bulk_id
    ]
    outcome = ApplyOutcome(applied=AppliedChange(change_id=change.change_id, applied_at=at))
    for row in sorted(targets, key=lambda target: target.sequence, reverse=True):
        if revert_change(state, row, user, at, outcome):
            outcome.undone_change_ids.append(row.stored.change.change_id)
    details: dict[str, JsonValue] = {
        "bulk_id": change.bulk_id,
        "undone": len(outcome.undone_change_ids),
        "kept": len(targets) - len(outcome.undone_change_ids),
    }
    outcome.events.append(
        AuditEvent(event=BULK_UNDONE, run_id=run_id, by=user, at=at, details=details)
    )
    return outcome


def revert_change(
    state: ReviewState, row: StoredChangeRow, user: str, at: datetime, outcome: ApplyOutcome
) -> bool:
    """Put back what one change replaced, if its target still holds what it wrote."""
    change = row.stored.change
    if isinstance(change, SetValueChange | PickAlternativeChange):
        return revert_output(state, change.record_id, change.field, row)
    if isinstance(change, AcceptWarningChange):
        return revert_acceptance(state, change.issue_id, row, user, at, outcome)
    if isinstance(change, ExcludeRecordChange | RestoreRecordChange):
        return revert_exclusion(state, change.record_id, row)
    return False


def read_entry(state_json: JsonValue, key: str) -> JsonValue:
    """Return one entry of a stored before/after state, or None."""
    return state_json.get(key) if isinstance(state_json, dict) else None


def revert_output(state: ReviewState, record_id: str, field: str, row: StoredChangeRow) -> bool:
    """Put back a field's earlier output section."""
    record = state.records[record_id]
    stored = record.fields[field]
    if stored.output.model_dump(mode="json") != read_entry(row.after_state, "output"):
        return False
    output = FieldOutput.model_validate(read_entry(row.before_state, "output"))
    fields = {**record.fields, field: stored.model_copy(update={"output": output})}
    state.records[record_id] = record.model_copy(update={"fields": fields})
    return True


def revert_acceptance(
    state: ReviewState,
    issue_id: str,
    row: StoredChangeRow,
    user: str,
    at: datetime,
    outcome: ApplyOutcome,
) -> bool:
    """Reopen a warning the bulk action accepted, if it is still accepted."""
    issue = state.issues.get(issue_id)
    if issue is None or row.after_state is None:
        return False
    if read_issue_state(issue.status, issue.closed_by) != row.after_state:
        return False
    state.issues[issue_id] = issue.model_copy(update={"status": "open", "closed_by": None})
    outcome.history.append(
        IssueHistoryEntry(
            issue_id=issue_id, action="opened", by=user, at=at, note=ACCEPTANCE_UNDONE_NOTE
        )
    )
    return True


def revert_exclusion(state: ReviewState, record_id: str, row: StoredChangeRow) -> bool:
    """Put back a record's earlier exclusion (or none)."""
    record = state.records[record_id]
    if dump_exclusion(record.exclusion) != read_entry(row.after_state, "exclusion"):
        return False
    before = read_entry(row.before_state, "exclusion")
    exclusion = Exclusion.model_validate(before) if before is not None else None
    state.records[record_id] = record.model_copy(update={"exclusion": exclusion})
    return True
