"""Interrupted runs: at app start, runs left in a processing status are marked failed.

Processing runs in a background thread, so a restart stops it midway. Each such run gets the
PROCESSING_INTERRUPTED run issue and the `failed` status, so the user can retry it.
"""

from datetime import datetime

from app.config.bundle import ConfigBundle
from app.contracts.issue import IssueHistoryEntry
from app.logging_setup import log_event
from app.runs.queries import PROCESSING_STATUSES
from app.storage.review_db import ReviewDatabase
from app.validation.issues import IssueDraft, make_issue

# Run issue code in the client's issue catalogue
PROCESSING_INTERRUPTED = "PROCESSING_INTERRUPTED"


def fail_interrupted_runs(database: ReviewDatabase, bundle: ConfigBundle, at: datetime) -> int:
    """Mark every run still in a processing status as failed; return how many were marked."""
    run_ids = [run.run_id for run in database.list_runs() if run.status in PROCESSING_STATUSES]
    for run_id in run_ids:
        mark_run_interrupted(database, bundle, run_id, at)
    # IDs and counts only
    log_event(
        "runs_interrupted",
        level="WARNING" if run_ids else "INFO",
        details={"run_count": len(run_ids)},
    )
    return len(run_ids)


def mark_run_interrupted(
    database: ReviewDatabase, bundle: ConfigBundle, run_id: str, at: datetime
) -> None:
    """Add the PROCESSING_INTERRUPTED run issue (history opened) and set the run to failed."""
    issue = make_issue(
        IssueDraft(code=PROCESSING_INTERRUPTED), bundle.issue_catalogue, bundle.field_rules
    )
    with database.transaction():
        # Keep any issue already stored; a repeated mark does not add the issue twice
        issues = [i for i in database.read_issues(run_id) if i.issue_id != issue.issue_id]
        database.write_issues(run_id, [*issues, issue])
        opened = IssueHistoryEntry(issue_id=issue.issue_id, action="opened", by=None, at=at)
        database.add_issue_history(run_id, [opened])
        database.set_run_status(run_id, "failed")
