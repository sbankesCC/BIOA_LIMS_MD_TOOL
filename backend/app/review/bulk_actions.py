"""Bulk action list: a run's bulk actions read from its stored changes, newest first.

Lets the review screen offer Undo for any bulk action, also after a reload. Read only.
"""

from collections.abc import Mapping, Sequence

from app.contracts.api import BulkActionSummary
from app.contracts.changes import AcceptWarningChange, BulkChangeType, Change, UndoBulkChange
from app.contracts.issue import Issue
from app.storage.review_db import StoredChangeRow


def list_bulk_actions(
    rows: Sequence[StoredChangeRow], issues: Sequence[Issue], is_in_review: bool
) -> list[BulkActionSummary]:
    """Return one summary per bulk ID in the run's changes, newest first."""
    issues_by_id = {issue.issue_id: issue for issue in issues}
    groups: dict[str, list[StoredChangeRow]] = {}
    undo_rows: dict[str, StoredChangeRow] = {}
    # Changes in saved order; an undo is kept apart from the bulk action it undoes
    for row in rows:
        change = row.stored.change
        if isinstance(change, UndoBulkChange):
            undo_rows.setdefault(change.bulk_id, row)
        elif change.bulk_id is not None:
            groups.setdefault(change.bulk_id, []).append(row)
    summaries = [
        summarize_bulk_action(bulk_id, group, undo_rows.get(bulk_id), issues_by_id, is_in_review)
        for bulk_id, group in groups.items()
    ]
    # The bulk action saved last comes first
    return list(reversed(summaries))


def summarize_bulk_action(
    bulk_id: str,
    group: Sequence[StoredChangeRow],
    undo_row: StoredChangeRow | None,
    issues_by_id: Mapping[str, Issue],
    is_in_review: bool,
) -> BulkActionSummary:
    """Return what one bulk action changed, who saved it, and whether it was undone."""
    changes = [row.stored.change for row in group]
    first = group[0]
    issue_codes = [find_issue_code(change, issues_by_id) for change in changes]
    record_ids = {find_record_id(change, issues_by_id) for change in changes} - {None}
    return BulkActionSummary(
        bulk_id=bulk_id,
        change_type=read_change_type(first.stored.change),
        field=next((field for field in map(find_field, changes) if field is not None), None),
        issue_code=next((code for code in issue_codes if code is not None), None),
        record_count=len(record_ids),
        change_count=len(changes),
        created_by=first.stored.user,
        created_at=first.stored.timestamp,
        is_pending=any(row.stored.status == "pending" for row in group),
        is_undone=undo_row is not None,
        undone_by=undo_row.stored.user if undo_row is not None else None,
        undone_at=undo_row.stored.timestamp if undo_row is not None else None,
        can_undo=undo_row is None and is_in_review,
    )


def read_change_type(change: Change) -> BulkChangeType:
    """Return the type of a change that is part of a bulk action (never an undo)."""
    if isinstance(change, UndoBulkChange):
        raise ValueError("An undo is not part of a bulk action.")
    return change.type


def find_field(change: Change) -> str | None:
    """Return the field a value change sets, or None for other change types."""
    return getattr(change, "field", None)


def find_issue_code(change: Change, issues_by_id: Mapping[str, Issue]) -> str | None:
    """Return the code of the issue an accepted warning closes, or None."""
    if not isinstance(change, AcceptWarningChange):
        return None
    issue = issues_by_id.get(change.issue_id)
    return issue.code if issue is not None else None


def find_record_id(change: Change, issues_by_id: Mapping[str, Issue]) -> str | None:
    """Return the record a change touches; an accepted warning touches its issue's record."""
    if isinstance(change, AcceptWarningChange):
        issue = issues_by_id.get(change.issue_id)
        return issue.record_id if issue is not None else None
    return getattr(change, "record_id", None)
