"""Plausibility review (CONTRACTS §3d): the records sent to the model and its findings.

Called inside Validation with only the values that passed the field checks. Code drops a
finding whose check ID was not inserted; every other finding becomes a warning.
"""

from app.contracts.base import ContractModel


class PlausibilityRecord(ContractModel):
    """One record to review: its ID, name, final values and found context values, by key."""

    record_id: str
    name: str | None
    values: dict[str, str]
    context: dict[str, str]


class PlausibilityFinding(ContractModel):
    """Values that do not make sense together under one check, with a reason for the reviewer."""

    record_id: str
    check_id: str
    fields: list[str]
    reason: str


class PlausibilityOutput(ContractModel):
    """The whole plausibility response: problems only, empty when there is nothing to report."""

    findings: list[PlausibilityFinding]
