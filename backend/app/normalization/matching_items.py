"""Matching items (4.7): a lookup value that stays unresolved is collected for Matching.

Only fields with `Matching allowed = yes` are collected. The field's normalized value stays
empty and the text goes in `matching_value`, which the Matching step reads.
"""

from pydantic import BaseModel

from app.config.business_rules import FieldDefinition


class UnresolvedValue(BaseModel):
    """What a field holds after an unsuccessful lookup match: its value and its matching value."""

    value: str | None
    matching_value: str | None = None


def collect_unresolved_value(rule: FieldDefinition, text: str) -> UnresolvedValue:
    """Return the value to keep for text that matched no lookup value.

    A field that allows Matching keeps no value and hands the text to Matching. Any other field
    keeps the text as written, and validation reports it.
    """
    if rule.matching_allowed:
        return UnresolvedValue(value=None, matching_value=text)
    return UnresolvedValue(value=text)
