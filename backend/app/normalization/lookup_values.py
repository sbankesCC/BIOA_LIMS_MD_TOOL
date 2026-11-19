"""Allowed lookup values: a field's lookup list without the excluded values (General rules table).

A row excludes a value for "all steps" or for one step (for example Matching). Rows match a
value exactly or by prefix; a row for "(all lists)" applies to every list.
"""

from collections.abc import Sequence

from pydantic import BaseModel

from app.config.business_rules import (
    ALL_LISTS,
    EXCLUDED_VALUES_HEADING,
    LOOKUP_LIST_COLUMN,
    BusinessRules,
    FieldDefinition,
)
from app.config.lookup_lists import LookupLists
from app.logging_setup import log_event

VALUE_COLUMN = "Value"
MATCH_COLUMN = "Match"
EXCLUDED_FROM_COLUMN = "Excluded from"
ALL_STEPS = "all steps"
MATCHING_STEP = "Matching"
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


# ----- Startup warning for large Matching lists -----

# A Matching-allowed list longer than this is worth a deliberate choice (cost grows with it)
LARGE_LIST_SIZE = 150


class LargeMatchingList(BaseModel):
    """A Matching-allowed field whose list is large and not cut by `MATCHING_SHORTLIST_SIZE`."""

    key: str
    size: int


def find_large_matching_lists(
    business_rules: BusinessRules, lookup_lists: LookupLists, shortlist_size: int | None
) -> list[LargeMatchingList]:
    """Return large Matching-allowed lists (over LARGE_LIST_SIZE values) the setting leaves whole.

    A list is left whole when the setting is blank or at least the list's size. A setting below
    the size is a deliberate cut, so it is not reported. Sizes count the values Matching may
    choose (excluded ones removed).
    """
    found: list[LargeMatchingList] = []
    for rule in business_rules.fields:
        if not rule.matching_allowed or rule.lookup_sheet is None:
            continue
        size = len(find_allowed_values(rule, business_rules, lookup_lists, MATCHING_STEP))
        is_cut = shortlist_size is not None and shortlist_size < size
        if size > LARGE_LIST_SIZE and not is_cut:
            found.append(LargeMatchingList(key=rule.key, size=size))
    return found


def log_large_matching_lists(
    business_rules: BusinessRules, lookup_lists: LookupLists, shortlist_size: int | None
) -> list[LargeMatchingList]:
    """Log a warning per large Matching list (field key and size) and return them."""
    found = find_large_matching_lists(business_rules, lookup_lists, shortlist_size)
    for large in found:
        log_event(
            "matching_list_large",
            level="WARNING",
            node=large.key,
            details={"list_size": large.size, "threshold": LARGE_LIST_SIZE},
        )
    return found
