"""Changes request (CONTRACTS §6): user changes sent from the UI, stored as pending.

Each change type is its own model, chosen by its `type` key. Rules that need the stored
run (reason when no open issue, current lookup values) are checked by the review service.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from app.contracts.base import ContractModel

ChangeStatus = Literal["pending", "applied"]


class SetValueChange(ContractModel):
    """Set a field's output value; null clears it."""

    type: Literal["set_value"]
    change_id: str
    record_id: str
    field: str
    value: str | None
    reason: str | None = None
    bulk_id: str | None = None


class PickAlternativeChange(ContractModel):
    """Choose one of a conflicting field's alternatives by its index."""

    type: Literal["pick_alternative"]
    change_id: str
    record_id: str
    field: str
    alternative_index: int = Field(ge=0)
    bulk_id: str | None = None


class AcceptWarningChange(ContractModel):
    """Accept a warning issue; individual-review warnings need the source viewed."""

    type: Literal["accept_warning"]
    change_id: str
    issue_id: str
    source_viewed: bool = False
    note: str | None = None
    bulk_id: str | None = None


class ExcludeRecordChange(ContractModel):
    """Leave a record out of the export; a reason is required."""

    type: Literal["exclude_record"]
    change_id: str
    record_id: str
    reason: str = Field(min_length=1)
    bulk_id: str | None = None


class RestoreRecordChange(ContractModel):
    """Bring an excluded record back."""

    type: Literal["restore_record"]
    change_id: str
    record_id: str
    bulk_id: str | None = None


class UndoBulkChange(ContractModel):
    """Undo every change that shares `bulk_id`."""

    type: Literal["undo_bulk"]
    change_id: str
    bulk_id: str


Change = Annotated[
    SetValueChange
    | PickAlternativeChange
    | AcceptWarningChange
    | ExcludeRecordChange
    | RestoreRecordChange
    | UndoBulkChange,
    Field(discriminator="type"),
]


class ChangesRequest(ContractModel):
    """The body of `POST /runs/{run_id}/changes`."""

    user: str
    timestamp: datetime
    changes: list[Change]


class StoredChange(ContractModel):
    """A change as kept in the review database: pending until the next re-check or Verify."""

    change: Change
    user: str
    timestamp: datetime
    status: ChangeStatus = "pending"
