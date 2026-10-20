"""Issue lifecycle (CONTRACTS §4a): merge a validation pass's issues with the earlier ones.

The same key gives the same issue ID, which keeps its accepted state. An earlier issue that is no
longer found was fixed by a change, so it becomes `resolved`. Issues validation does not own
(ingest, graph) and issues of skipped records (excluded) are kept as they are.
"""

from collections.abc import Sequence

from app.contracts.issue import Issue


def carry_state(issue: Issue, previous: Issue | None) -> Issue:
    """Return a found issue with the earlier accepted state, if it was accepted before."""
    if previous is None or previous.status != "accepted":
        return issue
    return issue.model_copy(update={"status": "accepted", "closed_by": previous.closed_by})


def is_kept_unchanged(issue: Issue, owned_codes: set[str], skipped_record_ids: set[str]) -> bool:
    """Return True for an earlier issue this pass did not look at, so it cannot judge it."""
    if issue.code not in owned_codes:
        return True
    return issue.record_id is not None and issue.record_id in skipped_record_ids


def merge_issues(
    previous: Sequence[Issue],
    found: Sequence[Issue],
    owned_codes: set[str],
    skipped_record_ids: set[str],
) -> list[Issue]:
    """Return this pass's issues (accepted state kept) plus earlier ones, resolved if gone."""
    previous_by_id = {issue.issue_id: issue for issue in previous}
    found_ids = {issue.issue_id for issue in found}
    merged = [carry_state(issue, previous_by_id.get(issue.issue_id)) for issue in found]
    # Earlier issues not found again: kept for the audit trail, resolved if validation owns them
    for issue in previous:
        if issue.issue_id in found_ids:
            continue
        if is_kept_unchanged(issue, owned_codes, skipped_record_ids) or issue.status == "resolved":
            merged.append(issue)
        else:
            merged.append(issue.model_copy(update={"status": "resolved", "closed_by": None}))
    return merged
