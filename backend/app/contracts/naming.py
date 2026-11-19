"""Naming (CONTRACTS §3c): the records sent to the model and the names it suggests.

One call per run. Code checks each suggested name (translation, length, characters, unique in
the run); a passing name is stored as the record name field's suggestion, never as its value.
"""

from app.contracts.base import ContractModel


class NamingRecord(ContractModel):
    """One record to name: its ID, the name as written, and its known values by key.

    `values` holds each extracted field's normalized value (the value as written when it could
    not be normalized); `context` holds the context attribute values that were found.
    """

    record_id: str
    name_as_written: str | None
    values: dict[str, str]
    context: dict[str, str]


class NameAnswer(ContractModel):
    """The model's name for one record, the `[Naming]` rule it followed, and why."""

    record_id: str
    name: str | None
    rule_id: str | None
    reason: str


class NamingOutput(ContractModel):
    """The whole Naming response: one answer per record."""

    names: list[NameAnswer]
