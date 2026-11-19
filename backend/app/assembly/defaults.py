"""Defaults (7.4): an empty extracted field takes its configured default.

Never on a conflicting field (the reviewer picks), and never when a value is waiting for
Matching or for a reviewer's choice: that field is not empty, it is unresolved.
"""

from app.config.business_rules import FieldDefinition
from app.contracts.record import FieldOutput, StoredField
from app.normalization.notes import TransformNote


def apply_default(rule: FieldDefinition, stored: StoredField, output: FieldOutput) -> FieldOutput:
    """Return the output with the field's default if it needs one, else unchanged."""
    if rule.default is None or not rule.is_extracted or output.value:
        return output
    if is_unresolved(stored):
        return output
    note = TransformNote(code="DEFAULT_APPLIED", value=rule.default)
    return FieldOutput(
        value=rule.default, origin="default", changes=[*output.changes, note.to_text()]
    )


def is_unresolved(stored: StoredField) -> bool:
    """Return True for an open conflict or a value waiting for Matching or a reviewer's choice."""
    if stored.extraction is not None and stored.extraction.status == "conflicting":
        return True
    normalization = stored.normalization
    return normalization is not None and bool(normalization.matching_value or normalization.choices)
