"""Review state: a working copy of a run's records and issues while changes are checked or applied.

Loaded from the review database, changed in memory, then written back in one transaction.
"""

from collections.abc import Sequence

from pydantic import BaseModel

from app.contracts.issue import Issue
from app.contracts.record import StoredRecord


class ReviewState(BaseModel):
    """A run's records and issues, keyed by ID, in their stored order."""

    records: dict[str, StoredRecord]
    issues: dict[str, Issue]

    def record_list(self) -> list[StoredRecord]:
        """Return the records in order."""
        return list(self.records.values())

    def issue_list(self) -> list[Issue]:
        """Return the issues in order."""
        return list(self.issues.values())


def make_review_state(records: Sequence[StoredRecord], issues: Sequence[Issue]) -> ReviewState:
    """Build a working copy from stored records and issues."""
    return ReviewState(
        records={record.record_id: record for record in records},
        issues={issue.issue_id: issue for issue in issues},
    )


def has_open_field_issue(state: ReviewState, record_id: str, field: str) -> bool:
    """Return True if the field has an open issue (so a change needs no reason)."""
    return any(
        issue.record_id == record_id and issue.field == field and issue.status == "open"
        for issue in state.issues.values()
    )
