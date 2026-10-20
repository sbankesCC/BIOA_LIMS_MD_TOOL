"""Lookup matching: match a cleaned value to its field's lookup list, and read Y/N booleans.

Order: exact match, then exactly one case-insensitive match, then exactly one normalized match
(ignoring case, spaces and the degree sign). A changed value gives FORMAT_CORRECTED; no single
match keeps the value as written and gives NOT_IN_LOOKUP.
"""

from collections.abc import Sequence

from pydantic import BaseModel

from app.transform.notes import TransformNote

# Characters a normalized match ignores, besides case
DEGREE_SIGN = "°"

# The two values a boolean loader field accepts (LabVantage Y/N flags)
BOOLEAN_VALUES = ("Y", "N")


class MatchResult(BaseModel):
    """The output value after matching, and the note for validation, if any."""

    value: str
    note: TransformNote | None = None


def normalize_for_match(text: str) -> str:
    """Return the text without case, whitespace or degree signs, for a normalized match."""
    without_degrees = text.replace(DEGREE_SIGN, "")
    return "".join(without_degrees.split()).casefold()


def find_single_match(value: str, allowed: Sequence[str]) -> str | None:
    """Return the one allowed value matching case-insensitively, else the one normalized match."""
    # Case-insensitive first: it changes the least
    case_matches = [option for option in allowed if option.casefold() == value.casefold()]
    if len(case_matches) == 1:
        return case_matches[0]
    # Then ignoring spaces and degree signs as well; two matches mean no decision
    normalized = normalize_for_match(value)
    normalized_matches = [option for option in allowed if normalize_for_match(option) == normalized]
    if len(normalized_matches) == 1:
        return normalized_matches[0]
    return None


def match_lookup_value(value: str, allowed: Sequence[str]) -> MatchResult:
    """Match a cleaned value to a lookup list; no single match keeps it as written."""
    # An exact match needs no note
    if value in allowed:
        return MatchResult(value=value)
    match = find_single_match(value, allowed)
    if match is None:
        note = TransformNote(code="NOT_IN_LOOKUP", original=value, value=value)
        return MatchResult(value=value, note=note)
    note = TransformNote(code="FORMAT_CORRECTED", original=value, value=match)
    return MatchResult(value=match, note=note)


def match_boolean_value(value: str) -> MatchResult:
    """Read a boolean as Y or N, ignoring case; anything else is kept as written."""
    # Y and N act as a two-value list; words such as "Yes" are not guessed
    return match_lookup_value(value, BOOLEAN_VALUES)
