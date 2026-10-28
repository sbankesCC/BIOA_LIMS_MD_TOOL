"""Issue (CONTRACTS §5): a problem found by validation, plus its history for the audit trail."""

from datetime import datetime
from typing import Literal

from pydantic import JsonValue

from app.contracts.base import ContractModel

IssueSeverity = Literal["error", "warning", "info"]
IssueStatus = Literal["open", "resolved", "accepted"]
IssueAction = Literal["opened", "accepted", "resolved"]


class Issue(ContractModel):
    """One issue; run-level issues have no record and no field.

    `individual_review` and `note_required` are the catalogue's flags for the issue's code.
    """

    issue_id: str
    code: str
    severity: IssueSeverity
    record_id: str | None
    field: str | None
    message: str
    individual_review: bool = False
    note_required: bool = False
    details: dict[str, JsonValue] = {}
    status: IssueStatus = "open"
    closed_by: str | None = None


class IssueHistoryEntry(ContractModel):
    """One step in an issue's life (opened, accepted, resolved): by whom and when."""

    issue_id: str
    action: IssueAction
    by: str | None
    at: datetime
    note: str | None = None


class DuplicateCandidate(ContractModel):
    """One existing type a duplicate issue names in `details.candidates` (CONTRACTS §5).

    `match`: `exact`, `normalized`, or the judge's verdict (`same`, `unsure`). Description, class
    and active flag are copied from the run's pinned reference data, or None when it has none.
    """

    candidate_id: str
    name: str
    match: str
    reason: str | None = None
    description: str | None = None
    consumable_class: str | None = None
    active_flag: str | None = None
