"""Derived-value check (8.5): a derived field a person set must agree with its derivation.

Assembly never overwrites a person's value, so it can differ from what the tables give. The
difference is not wrong, but a person confirms it (and notes why) with DERIVED_VALUE_MISMATCH.
"""

from app.assembly.assemble import USER_ORIGINS
from app.assembly.derivations import DERIVATIONS
from app.config.business_rules import BusinessRules
from app.contracts.record import StoredRecord
from app.validation import codes
from app.validation.issues import IssueDraft

# Shown for {derived} when the tables leave the field blank
BLANK_TEXT = "(blank)"


def check_derived_values(record: StoredRecord, business_rules: BusinessRules) -> list[IssueDraft]:
    """Return DERIVED_VALUE_MISMATCH for each person-set derived field that differs."""
    drafts: list[IssueDraft] = []
    for derive in DERIVATIONS:
        derived = derive(business_rules, record)
        stored = record.fields.get(derived.key) if derived is not None else None
        if derived is None or stored is None or stored.output.origin not in USER_ORIGINS:
            continue
        if is_same_value(stored.output.value, derived.value):
            continue
        drafts.append(
            IssueDraft(
                code=codes.DERIVED_VALUE_MISMATCH,
                record_id=record.record_id,
                field=derived.key,
                value=stored.output.value,
                message_values={"derived": derived.value or BLANK_TEXT},
                details={"derived": derived.value},
            )
        )
    return drafts


def is_same_value(typed: str | None, derived: str | None) -> bool:
    """Return True if the two values agree, ignoring case and surrounding spaces; blanks agree."""
    return (typed or "").strip().casefold() == (derived or "").strip().casefold()
