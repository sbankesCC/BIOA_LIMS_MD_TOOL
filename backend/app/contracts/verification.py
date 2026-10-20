"""Extraction verification output (CONTRACTS §3): problems the verification agent reports.

The agent never returns corrected values. Anything it does not list is treated as supported.
"""

from typing import Literal

from app.contracts.base import ContractModel

FieldVerdict = Literal["contradicted", "unsupported", "present_missed"]
RecordVerdict = Literal["not_a_consumable_type", "duplicate_within_run", "should_be_split"]

# Result of the code citation check, per field
CitationCheck = Literal["verified", "not_verified", "not_checkable"]


class FieldFinding(ContractModel):
    """A problem with one field of one record."""

    record_id: str
    field: str
    verdict: FieldVerdict
    sources: list[str]
    note: str


class RecordFinding(ContractModel):
    """A problem with a whole record."""

    record_id: str
    verdict: RecordVerdict
    note: str


class MissedCandidate(ContractModel):
    """A Consumable Type in the documents that extraction did not return."""

    name_as_written: str
    sources: list[str]
    reason: str


class ExcludedItemChallenge(ContractModel):
    """An excluded item the agent thinks may be a Consumable Type."""

    item: str
    reason: str


class UnreportedConflict(ContractModel):
    """Another source may give a different value for a field, not reported by extraction."""

    record_id: str
    field: str
    sources: list[str]
    note: str


class VerificationOutput(ContractModel):
    """The whole verification response; every list is empty when nothing is wrong."""

    field_findings: list[FieldFinding]
    record_findings: list[RecordFinding]
    missed_candidates: list[MissedCandidate]
    excluded_item_challenges: list[ExcludedItemChallenge]
    unreported_conflicts: list[UnreportedConflict]
