"""Reference data: a versioned snapshot of existing Consumable Types, for the duplicate check.

Built by the reference data admin (M7) from an upload, using the column names in
`reference_data_mapping.yaml`. Validation compares records against it.
"""

from app.contracts.base import ContractModel


class ReferenceType(ContractModel):
    """One existing Consumable Type; `candidate_id` (`ref_0001`) names it to the duplicate judge."""

    candidate_id: str
    name: str
    version: str
    description: str | None = None
    consumable_class: str | None = None
    active_flag: str | None = None
    version_status: str | None = None


class ReferenceData(ContractModel):
    """A reference data snapshot: its version and every existing type in it."""

    version: str
    types: list[ReferenceType]
