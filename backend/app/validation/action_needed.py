"""Action needed (CONTRACTS §4): what a record still needs, from its open issues.

Excluded records need nothing. Any open red issue means Fix; any open yellow means Check.
Grey issues and accepted warnings need no action.
"""

from collections.abc import Sequence

from app.contracts.issue import Issue
from app.contracts.record import ActionNeeded, StoredRecord


def compute_action_needed(record: StoredRecord, issues: Sequence[Issue]) -> ActionNeeded:
    """Return fix, check, none or excluded for one record."""
    if record.exclusion is not None:
        return "excluded"
    open_severities = {
        issue.severity
        for issue in issues
        if issue.record_id == record.record_id and issue.status == "open"
    }
    if "error" in open_severities:
        return "fix"
    if "warning" in open_severities:
        return "check"
    return "none"
