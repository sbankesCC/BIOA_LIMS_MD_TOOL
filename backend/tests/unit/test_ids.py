"""ID tests: numbered record IDs never repeat and issue IDs are stable for the same key."""

import pytest

from app.ids import IdCounter, make_issue_id, make_record_id_counter


def test_record_ids_start_at_one() -> None:
    """A new run's first record IDs are rec_0001, rec_0002."""
    counter = make_record_id_counter()
    assert [counter.next_id(), counter.next_id()] == ["rec_0001", "rec_0002"]


def test_record_ids_continue_after_existing_ones() -> None:
    """New records (e.g. after re-extraction) get numbers after the highest existing ID."""
    counter = make_record_id_counter(["rec_0003", "rec_0001"])
    assert counter.next_id() == "rec_0004"


def test_numbers_past_the_width_still_work() -> None:
    """IDs beyond 9999 keep counting without padding."""
    counter = IdCounter("rec_", ["rec_9999"])
    assert counter.next_id() == "rec_10000"


def test_existing_id_with_wrong_prefix_is_refused() -> None:
    """An existing ID that is not prefix + digits raises a plain error."""
    with pytest.raises(ValueError, match="is not a rec_"):
        make_record_id_counter(["iss_0001"])


def test_issue_id_is_stable_for_the_same_key() -> None:
    """The same code, record, field and value always give the same issue ID."""
    first = make_issue_id("TOO_LONG", "rec_0001", "synthetic_field", "synthetic value")
    second = make_issue_id("TOO_LONG", "rec_0001", "synthetic_field", "synthetic value")
    assert first == second
    assert first.startswith("iss_")
    assert len(first) == len("iss_") + 12


def test_issue_id_is_a_known_value() -> None:
    """The hash is fixed across versions and machines (guards against a changed key format)."""
    issue_id = make_issue_id("TOO_LONG", "rec_0001", "synthetic_field", "synthetic value")
    assert issue_id == "iss_bc9f558b3e6e"


def test_changed_value_gives_a_new_issue_id() -> None:
    """When the value changes, the issue key changes, so the ID changes."""
    before = make_issue_id("TOO_LONG", "rec_0001", "synthetic_field", "old value")
    after = make_issue_id("TOO_LONG", "rec_0001", "synthetic_field", "new value")
    assert before != after


def test_null_and_empty_values_give_different_issue_ids() -> None:
    """An empty string and a missing value are different keys."""
    assert make_issue_id("CODE", "rec_0001", "f", None) != make_issue_id(
        "CODE", "rec_0001", "f", ""
    )


def test_run_level_issue_id_is_stable() -> None:
    """Run-level issues (no record, no field) also get a stable ID."""
    assert make_issue_id("SCANNED_PAGES", None, None, None) == make_issue_id(
        "SCANNED_PAGES", None, None, None
    )
