"""Review service (ARCHITECTURE §4.9): saves changes as pending, re-checks, and verifies a run.

Works outside the graph, on the review database, and calls the Validation service directly.
Functions take the user as a parameter: the API passes the signed-in user (PILOT_USER).
"""

import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel

from app.contracts.changes import Change, StoredChange
from app.contracts.issue import Issue, IssueHistoryEntry
from app.contracts.record import StoredRecord
from app.contracts.reference import ReferenceData
from app.contracts.run import AuditEvent, RunInfo
from app.logging_setup import log_event
from app.review.apply_changes import ApplyOutcome, apply_change
from app.review.change_checks import check_change
from app.review.errors import RunNotInReviewError
from app.review.state import ReviewState, make_review_state
from app.review.view import ReviewCounts, count_review
from app.storage.review_db import ReviewDatabase, StoredChangeRow
from app.validation.judge_cache import DuplicateJudge, JudgeCache, JudgeRunner
from app.validation.service import (
    ValidationConfig,
    ValidationResult,
    attach_issues,
    validate_run,
)

# Audit events written by the review service (exclusions and undo are in apply_changes.py)
RUN_VERIFIED = "run_verified"
VERIFIED_LABEL_REMOVED = "verified_label_removed"

# Issue history note for warnings the verifier accepts
ACCEPTED_ON_VERIFY_NOTE = "accepted on Verify"


@dataclass(frozen=True)
class ReviewContext:
    """What a run is checked with: its captured config, the duplicate judge and reference data.

    The caller builds it from the config versions the run started with (ARCHITECTURE §6).
    """

    config: ValidationConfig
    judge: DuplicateJudge
    judge_cache: JudgeCache
    judge_prompt_version: str
    judge_call_limit: int | None
    reference: ReferenceData | None


class SaveResult(BaseModel):
    """Which changes were stored as pending, and which were ignored as already stored."""

    saved_change_ids: list[str]
    ignored_change_ids: list[str]


class RecheckResult(BaseModel):
    """What a re-check did: changes applied, updated counts, judge calls made."""

    applied_change_ids: list[str]
    counts: ReviewCounts
    judge_calls_made: int


class VerifyResult(BaseModel):
    """Verify's answer: verified, or the issues that block it; and warnings it accepted."""

    is_verified: bool
    blocking_errors: list[Issue]
    individual_review_warnings: list[Issue]
    accepted_warnings: list[Issue]
    counts: ReviewCounts


def require_in_review(database: ReviewDatabase, run_id: str) -> RunInfo:
    """Return the run if it is in review; raise RunNotInReviewError otherwise."""
    run = database.read_run(run_id)
    if run.status != "in_review":
        raise RunNotInReviewError(run_id)
    return run


def load_state(database: ReviewDatabase, run_id: str) -> ReviewState:
    """Load a run's records and issues as a working copy."""
    return make_review_state(database.read_records(run_id), database.read_issues(run_id))


# ----- Save changes -----


def save_changes(
    database: ReviewDatabase,
    context: ReviewContext,
    run_id: str,
    changes: Sequence[Change],
    user: str,
    at: datetime,
) -> SaveResult:
    """Check the changes and store new ones as pending; a resent `change_id` is ignored.

    Any rejected change rejects the whole request. Any saved change removes the verified label.
    """
    with database.transaction():
        run = require_in_review(database, run_id)
        new_changes, ignored_ids = split_new_changes(changes, database.read_change_ids(run_id))
        check_new_changes(database, context, run_id, new_changes)
        stored = [StoredChange(change=change, user=user, timestamp=at) for change in new_changes]
        database.add_changes(run_id, stored)
        if new_changes and run.is_verified:
            remove_verified_label(database, run_id, user, at)
    saved_ids = [change.change_id for change in new_changes]
    log_event(
        "changes_saved",
        run_id=run_id,
        details={"saved": len(saved_ids), "ignored": len(ignored_ids)},
    )
    return SaveResult(saved_change_ids=saved_ids, ignored_change_ids=ignored_ids)


def split_new_changes(
    changes: Sequence[Change], stored_ids: set[str]
) -> tuple[list[Change], list[str]]:
    """Return the changes not stored yet, and the IDs of the repeated ones."""
    seen = set(stored_ids)
    new_changes: list[Change] = []
    ignored_ids: list[str] = []
    for change in changes:
        if change.change_id in seen:
            ignored_ids.append(change.change_id)
            continue
        seen.add(change.change_id)
        new_changes.append(change)
    return new_changes, ignored_ids


def check_new_changes(
    database: ReviewDatabase, context: ReviewContext, run_id: str, changes: Sequence[Change]
) -> None:
    """Check each new change against the stored run; the first problem raises an error."""
    state = load_state(database, run_id)
    earlier = [row.stored.change for row in database.read_changes(run_id)]
    for change in changes:
        check_change(change, state, earlier, context.config)
        earlier.append(change)


def remove_verified_label(database: ReviewDatabase, run_id: str, user: str, at: datetime) -> None:
    """Remove the verified label after a change, with an audit event."""
    database.clear_verified(run_id)
    database.add_audit_events(
        [AuditEvent(event=VERIFIED_LABEL_REMOVED, run_id=run_id, by=user, at=at)]
    )


# ----- Re-check -----


def recheck_run(
    database: ReviewDatabase, context: ReviewContext, run_id: str, user: str, at: datetime
) -> RecheckResult:
    """Apply the pending changes in order, run the Validation service, and store the result."""
    started = time.monotonic()
    with database.transaction():
        require_in_review(database, run_id)
        state = load_state(database, run_id)
        applied_ids = apply_pending_changes(database, context, run_id, state, at)
        result = validate_state(database, context, run_id, state)
        store_validation(database, run_id, state.issue_list(), result, user, at)
    counts = count_review(result.records, result.issues)
    log_event(
        "run_rechecked",
        run_id=run_id,
        duration_ms=int((time.monotonic() - started) * 1000),
        details={
            "applied_changes": len(applied_ids),
            "open_errors": counts.open_errors,
            "open_warnings": counts.open_warnings,
            "judge_calls": result.judge_calls_made,
        },
    )
    return RecheckResult(
        applied_change_ids=applied_ids, counts=counts, judge_calls_made=result.judge_calls_made
    )


def apply_pending_changes(
    database: ReviewDatabase, context: ReviewContext, run_id: str, state: ReviewState, at: datetime
) -> list[str]:
    """Apply every pending change in the order saved; return their IDs."""
    rows = database.read_changes(run_id)
    applied_ids: list[str] = []
    for position in range(len(rows)):
        row = rows[position]
        if row.stored.status != "pending":
            continue
        outcome = apply_change(state, row, rows, run_id, context.config, at)
        store_outcome(database, run_id, row, outcome)
        # Keep the in-memory rows current, so a later undo in this pass sees them
        rows = update_rows(rows, position, outcome)
        applied_ids.append(row.stored.change.change_id)
    return applied_ids


def store_outcome(
    database: ReviewDatabase, run_id: str, row: StoredChangeRow, outcome: ApplyOutcome
) -> None:
    """Write what applying one change did: applied row, undone changes, history, audit events."""
    database.mark_change_applied(run_id, outcome.applied)
    for change_id in outcome.undone_change_ids:
        database.mark_change_undone(run_id, change_id, row.stored.change.change_id)
    database.add_issue_history(run_id, outcome.history)
    database.add_audit_events(outcome.events)


def update_rows(
    rows: list[StoredChangeRow], position: int, outcome: ApplyOutcome
) -> list[StoredChangeRow]:
    """Return the rows with one marked applied and the changes it undid marked undone."""
    row = rows[position]
    undo_id = row.stored.change.change_id
    updated = list(rows)
    updated[position] = row.model_copy(
        update={
            "stored": row.stored.model_copy(update={"status": "applied"}),
            "applied_at": outcome.applied.applied_at,
            "before_state": outcome.applied.before_state,
            "after_state": outcome.applied.after_state,
        }
    )
    for index, other in enumerate(updated):
        if other.stored.change.change_id in outcome.undone_change_ids:
            updated[index] = other.model_copy(update={"undone_by": undo_id})
    return updated


def validate_state(
    database: ReviewDatabase, context: ReviewContext, run_id: str, state: ReviewState
) -> ValidationResult:
    """Run the Validation service on the working copy, with the run's stored findings."""
    runner = JudgeRunner(
        context.judge,
        context.judge_cache,
        context.judge_prompt_version,
        context.judge_call_limit,
    )
    return validate_run(
        state.record_list(),
        context.config,
        runner,
        context.reference,
        database.read_findings(run_id),
        state.issue_list(),
    )


def store_validation(
    database: ReviewDatabase,
    run_id: str,
    previous: Sequence[Issue],
    result: ValidationResult,
    user: str,
    at: datetime,
) -> None:
    """Store the validated records and issues; issues resolved now are closed by the user."""
    issues = close_resolved_issues(previous, result.issues, user)
    database.write_records(run_id, result.records)
    database.write_issues(run_id, issues)
    database.add_issue_history(run_id, find_history_steps(previous, issues, user, at))


def is_newly_resolved(issue: Issue, before: Issue | None) -> bool:
    """Return True if this pass resolved the issue."""
    return issue.status == "resolved" and before is not None and before.status != "resolved"


def close_resolved_issues(
    previous: Sequence[Issue], current: Sequence[Issue], user: str
) -> list[Issue]:
    """Return the issues with `closed_by` set to the user on those this re-check resolved."""
    before_by_id = {issue.issue_id: issue for issue in previous}
    return [
        issue.model_copy(update={"closed_by": user})
        if is_newly_resolved(issue, before_by_id.get(issue.issue_id))
        else issue
        for issue in current
    ]


def find_history_steps(
    previous: Sequence[Issue], current: Sequence[Issue], user: str, at: datetime
) -> list[IssueHistoryEntry]:
    """Return the history steps of this pass: issues opened (or reopened) and resolved."""
    before_by_id = {issue.issue_id: issue for issue in previous}
    steps: list[IssueHistoryEntry] = []
    for issue in current:
        before = before_by_id.get(issue.issue_id)
        is_opened = before is None or (before.status == "resolved" and issue.status != "resolved")
        if is_opened:
            steps.append(
                IssueHistoryEntry(issue_id=issue.issue_id, action="opened", by=None, at=at)
            )
        elif is_newly_resolved(issue, before):
            steps.append(
                IssueHistoryEntry(issue_id=issue.issue_id, action="resolved", by=user, at=at)
            )
    return steps


# ----- Verify -----


def verify_run(
    database: ReviewDatabase, context: ReviewContext, run_id: str, user: str, at: datetime
) -> VerifyResult:
    """Re-check, then return the blockers, or accept the other warnings and set the label.

    Red issues and open individual-review warnings block; excluded records' issues are ignored.
    """
    with database.transaction():
        recheck_run(database, context, run_id, user, at)
        records = database.read_records(run_id)
        issues = database.read_issues(run_id)
        live = find_live_issues(records, issues)
        errors = [issue for issue in live if issue.severity == "error"]
        individual = [i for i in live if i.severity == "warning" and i.individual_review]
        # Blocked: nothing is accepted and the label is not set
        if errors or individual:
            return VerifyResult(
                is_verified=False,
                blocking_errors=errors,
                individual_review_warnings=individual,
                accepted_warnings=[],
                counts=count_review(records, issues),
            )
        warnings = [issue for issue in live if issue.severity == "warning"]
        result = accept_on_verify(database, run_id, warnings, user, at)
        database.set_verified(run_id, user, at)
        record_verification(database, run_id, len(warnings), user, at)
    return result


def find_live_issues(records: Sequence[StoredRecord], issues: Sequence[Issue]) -> list[Issue]:
    """Return open issues that are not on excluded records (run issues included)."""
    excluded_ids = {record.record_id for record in records if record.exclusion is not None}
    return [
        issue for issue in issues if issue.status == "open" and issue.record_id not in excluded_ids
    ]


def accept_on_verify(
    database: ReviewDatabase, run_id: str, warnings: Sequence[Issue], user: str, at: datetime
) -> VerifyResult:
    """Accept the remaining warnings for the verifier and update each record's action needed."""
    accepted_ids = {warning.issue_id for warning in warnings}
    issues = [
        issue.model_copy(update={"status": "accepted", "closed_by": user})
        if issue.issue_id in accepted_ids
        else issue
        for issue in database.read_issues(run_id)
    ]
    records = [attach_issues(record, issues) for record in database.read_records(run_id)]
    database.write_issues(run_id, issues)
    database.write_records(run_id, records)
    database.add_issue_history(
        run_id,
        [
            IssueHistoryEntry(
                issue_id=issue_id, action="accepted", by=user, at=at, note=ACCEPTED_ON_VERIFY_NOTE
            )
            for issue_id in sorted(accepted_ids)
        ],
    )
    return VerifyResult(
        is_verified=True,
        blocking_errors=[],
        individual_review_warnings=[],
        accepted_warnings=[issue for issue in issues if issue.issue_id in accepted_ids],
        counts=count_review(records, issues),
    )


def record_verification(
    database: ReviewDatabase, run_id: str, accepted_count: int, user: str, at: datetime
) -> None:
    """Write the audit event and log line for a verified run."""
    database.add_audit_events(
        [
            AuditEvent(
                event=RUN_VERIFIED,
                run_id=run_id,
                by=user,
                at=at,
                details={"accepted_warnings": accepted_count},
            )
        ]
    )
    log_event("run_verified", run_id=run_id, details={"accepted_warnings": accepted_count})
