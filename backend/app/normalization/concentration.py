"""Concentration (4.6): a number followed by a concentration unit gives the number.

The field's "Concentration units" table says what counts as a unit: a `Unit pattern` cell with
`contains "<text>"` accepts any unit holding that text; any other row accepts the units listed in
its `Examples` cell. Anything else (a ratio, a multiplier, a bare number, other text) is left
blank with a NOT_A_CONCENTRATION note. LabVantage accepts numbers only, so the unit is dropped.
"""

import re

from pydantic import BaseModel

from app.config.business_rules import FieldDefinition, split_list_cell
from app.normalization.notes import TransformNote
from app.normalization.numbers import format_plain_number, split_leading_number

UNITS_HEADING = "Concentration units"
PATTERN_COLUMN = "Unit pattern"
EXAMPLES_COLUMN = "Examples"

# `contains "<text>"` inside a Unit pattern cell
CONTAINS_PATTERN = re.compile(r'contains "([^"]+)"')


class ConcentrationResult(BaseModel):
    """The concentration number (None when blank) and the note for the reviewer, if any."""

    value: str | None
    note: TransformNote | None = None


class ConcentrationUnits(BaseModel):
    """What counts as a concentration unit: text a unit must contain, and listed units."""

    markers: list[str] = []
    listed: list[str] = []


def has_concentration_units(rule: FieldDefinition) -> bool:
    """Return True if the field has a Concentration units table (so it holds concentrations)."""
    return any(table.heading == UNITS_HEADING for table in rule.tables)


def read_concentration_units(rule: FieldDefinition) -> ConcentrationUnits:
    """Read the active rows of the field's Concentration units table."""
    units = ConcentrationUnits()
    for table in rule.tables:
        if table.heading != UNITS_HEADING:
            continue
        for row in table.active_rows():
            units.markers += CONTAINS_PATTERN.findall(row[PATTERN_COLUMN])
            units.listed += [remove_spaces(unit) for unit in split_list_cell(row[EXAMPLES_COLUMN])]
    return units


def remove_spaces(text: str) -> str:
    """Return the text without any whitespace, so "% w/v" and "%w/v" compare equal."""
    return "".join(text.split())


def is_concentration_unit(unit: str, units: ConcentrationUnits) -> bool:
    """Return True if the text is a concentration unit by the table's patterns or examples."""
    if not unit:
        return False
    if any(marker in unit for marker in units.markers):
        return True
    return remove_spaces(unit) in units.listed


def classify_concentration(text: str, units: ConcentrationUnits) -> ConcentrationResult:
    """Return the number when a concentration unit follows it; else blank with a note."""
    parts = split_leading_number(text)
    if parts is not None and is_concentration_unit(parts[1], units):
        number = format_plain_number(parts[0])
        if number is not None:
            # Scientific notation or thousands commas were read; say so for the reviewer
            note = None
            if number != parts[0]:
                note = TransformNote(code="NUMBER_READ_FROM_TEXT", original=text, value=number)
            return ConcentrationResult(value=number, note=note)
    note = TransformNote(code="NOT_A_CONCENTRATION", original=text, value=None)
    return ConcentrationResult(value=None, note=note)
