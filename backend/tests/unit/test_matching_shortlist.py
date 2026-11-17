"""Matching shortlist tests: the setting is a cost control for huge lists, never a default cut.

Lists here are synthetic; the real lists are read from the client config.
"""

import logging

import pytest

from app.config.bundle import ConfigBundle
from app.config.business_rules import FieldDefinition
from app.config.lookup_lists import LookupLists
from app.logging_setup import LOGGER_NAME
from app.normalization.lookup_matching import find_similar_values
from app.normalization.lookup_values import (
    LARGE_LIST_SIZE,
    find_large_matching_lists,
    log_large_matching_lists,
)

SYNTHETIC_VALUES = [f"Synthetic value {number}" for number in range(40)]


def test_blank_setting_always_passes_the_whole_list() -> None:
    """With no size set, every value is offered, however unlike the text they are."""
    assert find_similar_values("LN2 vapor phase", SYNTHETIC_VALUES, None) == SYNTHETIC_VALUES


@pytest.mark.parametrize("size", [40, 41, 1000])
def test_list_at_or_under_the_size_is_never_cut(size: int) -> None:
    """A list no longer than the setting is passed whole, in its own order."""
    assert find_similar_values("LN2 vapor phase", SYNTHETIC_VALUES, size) == SYNTHETIC_VALUES


def test_list_over_the_size_is_cut_to_that_size() -> None:
    """Only a list longer than the setting is narrowed (by text similarity)."""
    assert len(find_similar_values("Synthetic value 7", SYNTHETIC_VALUES, 5)) == 5


def matching_field(bundle: ConfigBundle) -> FieldDefinition:
    """Return a Matching-allowed field with a lookup list."""
    return next(r for r in bundle.business_rules.fields if r.matching_allowed and r.lookup_sheet)


def with_list_size(bundle: ConfigBundle, field: FieldDefinition, size: int) -> LookupLists:
    """Return the lookup lists with this field's list replaced by `size` synthetic values."""
    assert field.lookup_sheet is not None
    values = [f"Synthetic list value {number}" for number in range(size)]
    sheets = {**bundle.lookup_lists.sheets, field.lookup_sheet: values}
    return bundle.lookup_lists.model_copy(update={"sheets": sheets})


def test_todays_matching_lists_do_not_trigger_the_warning(bundle: ConfigBundle) -> None:
    """No Matching-allowed list in the client config is near the threshold."""
    sizes = [
        len(bundle.lookup_lists.sheets[rule.lookup_sheet])
        for rule in bundle.business_rules.fields
        if rule.matching_allowed and rule.lookup_sheet
    ]
    assert max(sizes) < LARGE_LIST_SIZE
    rules, lists = bundle.business_rules, bundle.lookup_lists
    assert find_large_matching_lists(rules, lists, None) == []


def test_a_large_list_left_whole_is_reported_with_its_size(bundle: ConfigBundle) -> None:
    """Over the threshold with a blank setting, or a setting at least the list's size, warns."""
    field = matching_field(bundle)
    size = LARGE_LIST_SIZE + 1
    lists = with_list_size(bundle, field, size)
    for setting in (None, size, size + 50):
        [large] = find_large_matching_lists(bundle.business_rules, lists, setting)
        assert (large.key, large.size) == (field.key, size)


def test_a_deliberate_cut_or_a_list_at_the_threshold_is_not_reported(bundle: ConfigBundle) -> None:
    """A setting below the list's size is a choice; a list of exactly the threshold is fine."""
    field = matching_field(bundle)
    large = with_list_size(bundle, field, LARGE_LIST_SIZE + 1)
    assert find_large_matching_lists(bundle.business_rules, large, LARGE_LIST_SIZE) == []
    at_threshold = with_list_size(bundle, field, LARGE_LIST_SIZE)
    assert find_large_matching_lists(bundle.business_rules, at_threshold, None) == []


def test_a_large_list_that_is_not_matching_allowed_is_ignored(bundle: ConfigBundle) -> None:
    """Manufacturer-sized lists matter only for fields that use Matching."""
    field = next(
        r for r in bundle.business_rules.fields if r.lookup_sheet and not r.matching_allowed
    )
    lists = with_list_size(bundle, field, 1000)
    assert find_large_matching_lists(bundle.business_rules, lists, None) == []


def test_the_warning_logs_the_field_and_its_size_without_blocking(
    bundle: ConfigBundle, caplog: pytest.LogCaptureFixture
) -> None:
    """Startup logs one warning line per large list with the field key and the sizes."""
    field = matching_field(bundle)
    lists = with_list_size(bundle, field, LARGE_LIST_SIZE + 5)
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        found = log_large_matching_lists(bundle.business_rules, lists, None)
    assert len(found) == 1
    [line] = [r.getMessage() for r in caplog.records if r.name == LOGGER_NAME]
    assert '"matching_list_large"' in line
    assert f'"node": "{field.key}"' in line
    assert f'"list_size": {LARGE_LIST_SIZE + 5}' in line
