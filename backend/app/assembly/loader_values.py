"""Loader values (7.2): an extracted field's output from its normalized value.

The output carries the normalization notes, so validation reads one place. A closed conflict
adds its own note; an open conflict stays empty for the reviewer to pick a value.
"""

from app.assembly.conflicts import find_closed_conflict
from app.config.business_rules import FieldDefinition
from app.contracts.record import FieldOutput, StoredField, find_initial_origin


def build_loader_value(rule: FieldDefinition, stored: StoredField) -> FieldOutput:
    """Return the output of an extracted field: its normalized value, notes and origin."""
    origin = find_initial_origin(rule)
    normalization = stored.normalization
    if normalization is None:
        return FieldOutput(value=None, origin=origin)
    closed = find_closed_conflict(stored)
    if closed is not None:
        changes = [*normalization.notes, closed.note.to_text()]
        return FieldOutput(value=closed.value, origin=origin, changes=changes)
    return FieldOutput(value=normalization.value, origin=origin, changes=list(normalization.notes))
