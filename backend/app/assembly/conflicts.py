"""Conflicts (7.1): alternatives that are identical after normalization are one value.

GEN-08: values from different sources are compared after normalization and translation. If they
become the same value, it is used and the field is noted. Alternatives that still differ stay a
conflict for the reviewer (validation reports it).
"""

from pydantic import BaseModel

from app.contracts.record import StoredField
from app.normalization.notes import TransformNote


class ClosedConflict(BaseModel):
    """The one value a conflict closed to, and the note saying so."""

    value: str
    note: TransformNote


def find_closed_conflict(stored: StoredField) -> ClosedConflict | None:
    """Return the closed conflict of a conflicting field whose alternatives agree, else None."""
    extraction = stored.extraction
    normalization = stored.normalization
    if extraction is None or extraction.status != "conflicting" or normalization is None:
        return None
    distinct = set(normalization.alternatives)
    # Several different values, or an alternative with no value, stay open
    if len(distinct) != 1 or "" in distinct:
        return None
    value = distinct.pop()
    written = sorted({write_alternative(item.value) for item in extraction.alternatives})
    note = TransformNote(code="CONFLICT_CLOSED", original=" | ".join(written), value=value)
    return ClosedConflict(value=value, note=note)


def write_alternative(value: str | list[str]) -> str:
    """Return an extracted alternative as one text (a multi-value list is joined with a comma)."""
    return value if isinstance(value, str) else ", ".join(value)
