"""Cleaning tests: trimming, collapsing whitespace and removing control characters, with notes."""

from app.transform.cleaning import clean_text
from app.transform.notes import COLLAPSED_SPACES, REMOVED_CONTROL_CHARACTERS, TRIMMED_WHITESPACE


def test_clean_value_is_unchanged_without_notes() -> None:
    """A value that needs no clean-up comes back as it is, with no notes."""
    cleaned = clean_text("Synthetic buffer A")
    assert cleaned.value == "Synthetic buffer A"
    assert cleaned.notes == []


def test_whitespace_at_ends_is_trimmed() -> None:
    """Leading and trailing whitespace is removed and noted."""
    cleaned = clean_text("  Synthetic buffer \n")
    assert cleaned.value == "Synthetic buffer"
    assert cleaned.notes == [TRIMMED_WHITESPACE]


def test_inner_whitespace_runs_collapse_to_one_space() -> None:
    """Runs of spaces, tabs and line breaks inside a value become one space."""
    cleaned = clean_text("Synthetic \t buffer\nA B")
    assert cleaned.value == "Synthetic buffer A B"
    assert cleaned.notes == [COLLAPSED_SPACES]


def test_control_characters_are_removed() -> None:
    """Control characters that are not whitespace are dropped and noted."""
    cleaned = clean_text("Synthetic\x07 buffer\x00")
    assert cleaned.value == "Synthetic buffer"
    assert cleaned.notes == [REMOVED_CONTROL_CHARACTERS]


def test_whitespace_only_value_becomes_empty() -> None:
    """A value of only whitespace cleans to an empty string."""
    assert clean_text(" \t ").value == ""
