"""Allowed lookup values: a field's lookup list without the excluded values (General rules table).

A row excludes a value for "all steps" or for one step (for example Matching). Rows match a
value exactly or by prefix; a row for "(all lists)" applies to every list.
"""

from collections.abc import Sequence

from app.config.business_rules import (
    ALL_LISTS,
    EXCLUDED_VALUES_HEADING,
    LOOKUP_LIST_COLUMN,
    BusinessRules,
    FieldDefinition,
)
from app.config.lookup_lists import LookupLists

VALUE_COLUMN = "Value"
MATCH_COLUMN = "Match"
EXCLUDED_FROM_COLUMN = "Excluded from"
ALL_STEPS = "all steps"
PREFIX_MATCH = "prefix"


def find_allowed_values(
    rule: FieldDefinition, business_rules: BusinessRules, lookup_lists: LookupLists, step: str
) -> list[str]:
    """Return the field's lookup list values that `step` may choose (excluded ones removed)."""
    if rule.lookup_sheet is None:
        return []
    values = lookup_lists.sheets.get(rule.lookup_sheet, [])
    excluded_rows = find_excluded_rows(rule.lookup_sheet, business_rules, step)
    return [value for value in values if not is_excluded(value, excluded_rows)]


def find_excluded_rows(
    sheet: str, business_rules: BusinessRules, step: str
) -> list[dict[str, str]]:
    """Return the active exclusion rows for this list that apply to the step."""
    tables = [
        table for table in business_rules.general.tables if table.heading == EXCLUDED_VALUES_HEADING
    ]
    if not tables:
        return []
    return [
        row
        for row in tables[0].active_rows()
        if row[LOOKUP_LIST_COLUMN] in (ALL_LISTS, sheet)
        and row[EXCLUDED_FROM_COLUMN] in (ALL_STEPS, step)
    ]


def is_excluded(value: str, excluded_rows: Sequence[dict[str, str]]) -> bool:
    """Return True if any exclusion row matches the value."""
    for row in excluded_rows:
        if row[MATCH_COLUMN] == PREFIX_MATCH and value.startswith(row[VALUE_COLUMN]):
            return True
        if row[MATCH_COLUMN] != PREFIX_MATCH and value == row[VALUE_COLUMN]:
            return True
    return False
