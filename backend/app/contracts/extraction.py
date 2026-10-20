"""Extraction output (CONTRACTS §2): what the extraction LLM returns, values copied as written.

Field keys are not fixed here: they come from `field_rules.yaml`. `status_rules.py` checks the
status table and the field set after parsing.
"""

from typing import Literal

from app.contracts.base import ContractModel

FieldStatus = Literal["found", "conflicting", "not_found"]

# A value is one string, or a list of strings for a `multi_value` field
ExtractedValue = str | list[str]


class Evidence(ContractModel):
    """One place a value was found: the chunk and the exact sentence or table row."""

    chunk_id: str
    quote: str


class Alternative(ContractModel):
    """One of the different values given for a conflicting field, with its evidence."""

    value: ExtractedValue
    evidence: list[Evidence]


class ExtractedField(ContractModel):
    """One field of one record as the LLM returned it."""

    status: FieldStatus
    value: ExtractedValue | None = None
    evidence: list[Evidence] = []
    alternatives: list[Alternative] = []
    allows_equivalent: bool = False
    warning: str | None = None


class ExtractedRecord(ContractModel):
    """One candidate Consumable Type; `record_ref` is temporary and replaced by a record ID."""

    record_ref: str
    found_in: list[str]
    record_summary: str
    record_warning: str | None = None
    fields: dict[str, ExtractedField]


class ExcludedItem(ContractModel):
    """Something the LLM considered and left out, with its reason and sources."""

    item: str
    reason: str
    chunk_ids: list[str]


class ExtractionOutput(ContractModel):
    """The whole extraction response: records and excluded items."""

    records: list[ExtractedRecord]
    excluded_items: list[ExcludedItem]
