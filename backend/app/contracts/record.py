"""Stored record (CONTRACTS §4): one record with a section per layer, for every loader field.

Each layer writes only its own section. Field and context attribute keys come from
`business_rules.md`, so the check that a record holds every one takes the business rules as input.
"""

from datetime import datetime
from typing import Literal

from app.config.business_rules import BusinessRules, FieldDefinition
from app.contracts.base import ContractModel
from app.contracts.extraction import ExtractedField
from app.contracts.verification import CitationCheck, FieldVerdict, RecordFinding

Origin = Literal[
    "extracted",
    "default",
    "derived",
    "from_suggestion",
    "fixed",
    "user_edited",
    "blank_for_now",
    "system",
]
ActionNeeded = Literal["fix", "check", "none", "excluded"]

# The model step that made a suggestion
SuggestionSource = Literal["matching", "naming"]


def find_initial_origin(rule: FieldDefinition) -> Origin:
    """Return a field's first origin: `extracted` if the model extracts it, else its role."""
    if rule.is_extracted:
        return "extracted"
    if rule.role == "derived" or rule.role == "system":
        return rule.role
    return "blank_for_now"


class RecordExtraction(ContractModel):
    """Record-level extraction section, wrapped by code from the extraction response."""

    record_ref: str
    record_summary: str
    record_warning: str | None = None


class RecordVerification(ContractModel):
    """Record-level verification section: record findings and whether it was re-extracted."""

    findings: list[RecordFinding] = []
    re_extracted: bool = False


class Exclusion(ContractModel):
    """Who excluded a record, when, and why."""

    by: str
    at: datetime
    reason: str


class FieldVerification(ContractModel):
    """Field-level verification: the code citation check and the agent's verdict, if any."""

    citation_check: CitationCheck | None = None
    verdict: FieldVerdict | None = None
    note: str | None = None


class FieldNormalization(ContractModel):
    """Field-level normalization: the normalized value, or a conflict's normalized alternatives.

    `matching_value` is the value sent to Matching (else None); `choices` are the list values a
    "Reviewer chooses" translation row offers.
    """

    value: str | None = None
    alternatives: list[str] = []
    notes: list[str] = []
    matching_value: str | None = None
    choices: list[str] = []


class Suggestion(ContractModel):
    """A value a model step proposes for a field; never applied until a person uses it."""

    value: str
    source: SuggestionSource
    reason: str
    rule_id: str | None = None


class FieldOutput(ContractModel):
    """Field-level output: the loader value (always text or empty), its origin and clean-ups."""

    value: str | None = None
    origin: Origin
    changes: list[str] = []
    selected_alternative: int | None = None


class StoredField(ContractModel):
    """One field of a stored record; `extraction` and `verification` are null if not extracted."""

    extraction: ExtractedField | None = None
    verification: FieldVerification | None = None
    normalization: FieldNormalization | None = None
    suggestion: Suggestion | None = None
    output: FieldOutput
    issue_ids: list[str] = []


class StoredContextAttribute(ContractModel):
    """One context attribute of a stored record: extraction and verification only, no output."""

    extraction: ExtractedField | None = None
    verification: FieldVerification | None = None


class StoredRecord(ContractModel):
    """A stored record with its sections, one entry per context attribute and per loader field."""

    record_id: str
    found_in: list[str]
    extraction: RecordExtraction
    verification: RecordVerification = RecordVerification()
    exclusion: Exclusion | None = None
    context: dict[str, StoredContextAttribute] = {}
    fields: dict[str, StoredField]
    issue_ids: list[str] = []
    action_needed: ActionNeeded = "none"


def find_record_field_problems(record: StoredRecord, business_rules: BusinessRules) -> list[str]:
    """Return a problem for each loader field or context attribute missing, and each unknown key."""
    field_keys = [field.key for field in business_rules.fields]
    context_keys = [attribute.key for attribute in business_rules.context_fields()]
    return find_key_problems(record.record_id, "field", field_keys, list(record.fields)) + (
        find_key_problems(record.record_id, "context attribute", context_keys, list(record.context))
    )


def find_key_problems(
    record_id: str, kind: str, expected_keys: list[str], keys: list[str]
) -> list[str]:
    """Return a problem for each expected key the record lacks and each key it should not have."""
    problems: list[str] = []
    # Every loader field (whatever its role) and every context attribute must be present
    for key in expected_keys:
        if key not in keys:
            problems.append(f"Record {record_id} has no entry for {kind} '{key}'.")
    # Keys the business rules do not define would never be read
    for key in keys:
        if key not in expected_keys:
            problems.append(f"Record {record_id} has unknown {kind} '{key}'.")
    return problems
