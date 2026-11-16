"""Field translation tables (4.3): a document phrase or temperature to a lookup value.

Rows are checked top to bottom; the first match applies. Phrase rows match the whole value
ignoring case, spaces and the degree sign. Range rows match a single stated temperature from Min
to Max, inclusive. A row with no lookup value and a "Reviewer chooses" list leaves the value blank
for the reviewer.
"""

import re

from pydantic import BaseModel

from app.config.business_rules import (
    ENTRY_COLUMN,
    LOOKUP_VALUE_COLUMN,
    REVIEWER_CHOOSES_COLUMN,
    FieldDefinition,
    is_blank_cell,
    split_list_cell,
)
from app.normalization.lookup_matching import normalize_for_match

TRANSLATION_HEADING = "Translation table"
MATCH_TYPE_COLUMN = "Match type"
WORDING_COLUMN = "Document wording"
MINIMUM_COLUMN = "Min °C"
MAXIMUM_COLUMN = "Max °C"
PHRASE_ROW = "phrase"
RANGE_ROW = "range"

# A value that is one temperature: a number, an optional degree sign and an optional C
SINGLE_TEMPERATURE = re.compile(r"\s*([-+]?\d+(?:\.\d+)?)\s*°?\s*c?\s*", re.IGNORECASE)


class Translation(BaseModel):
    """What a translation row says: the lookup value, or the values a reviewer chooses from."""

    entry: str
    value: str | None = None
    choices: list[str] = []


def find_translation(rule: FieldDefinition, text: str) -> Translation | None:
    """Return the first translation row that matches the text, or None (no table or no match)."""
    tables = [table for table in rule.tables if table.heading == TRANSLATION_HEADING]
    if not tables:
        return None
    for row in tables[0].active_rows():
        if is_row_match(row, text):
            return build_translation(row)
    return None


def is_row_match(row: dict[str, str], text: str) -> bool:
    """Return True if the text matches the row by its match type."""
    if row[MATCH_TYPE_COLUMN] == PHRASE_ROW:
        wanted = normalize_for_match(text)
        phrases = split_list_cell(row[WORDING_COLUMN])
        return any(normalize_for_match(phrase) == wanted for phrase in phrases)
    if row[MATCH_TYPE_COLUMN] == RANGE_ROW:
        return is_temperature_in_range(row, text)
    return False


def is_temperature_in_range(row: dict[str, str], text: str) -> bool:
    """Return True if the text is one temperature between the row's Min and Max, inclusive."""
    match = SINGLE_TEMPERATURE.fullmatch(text)
    if match is None:
        return False
    return float(row[MINIMUM_COLUMN]) <= float(match.group(1)) <= float(row[MAXIMUM_COLUMN])


def build_translation(row: dict[str, str]) -> Translation:
    """Turn a matched row into its lookup value or its reviewer choices."""
    lookup_value = row[LOOKUP_VALUE_COLUMN]
    if is_blank_cell(lookup_value):
        choices = split_list_cell(row[REVIEWER_CHOOSES_COLUMN])
        return Translation(entry=row[ENTRY_COLUMN], choices=choices)
    return Translation(entry=row[ENTRY_COLUMN], value=lookup_value)
