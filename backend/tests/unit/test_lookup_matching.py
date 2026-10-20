"""Lookup matching tests: exact, single case-insensitive, normalized, ambiguous and no match.

Lists here are synthetic; client lookup values are only used through the config (test_transform).
"""

from app.transform.lookup_matching import match_boolean_value, match_lookup_value
from app.transform.notes import TransformNote

SYNTHETIC_LIST = ["Synthetic Cold", "-5X", "Synthetic Tube 1 mL"]


def test_exact_match_has_no_note() -> None:
    """A value already on the list is kept with no note."""
    result = match_lookup_value("Synthetic Cold", SYNTHETIC_LIST)
    assert result.value == "Synthetic Cold"
    assert result.note is None


def test_single_case_insensitive_match_is_format_corrected() -> None:
    """A value differing only in case takes the list's spelling, noted as FORMAT_CORRECTED."""
    result = match_lookup_value("synthetic COLD", SYNTHETIC_LIST)
    assert result.value == "Synthetic Cold"
    assert result.note == TransformNote(
        code="FORMAT_CORRECTED", original="synthetic COLD", value="Synthetic Cold"
    )


def test_normalized_match_ignores_spaces_and_degree_sign() -> None:
    """Spaces and the degree sign are ignored, so "-5 °X" matches "-5X"."""
    result = match_lookup_value("-5 °x", SYNTHETIC_LIST)
    assert result.value == "-5X"
    assert result.note is not None
    assert result.note.code == "FORMAT_CORRECTED"
    assert result.note.original == "-5 °x"


def test_normalized_match_ignores_missing_spaces() -> None:
    """A value written without spaces still matches the spaced list value."""
    result = match_lookup_value("synthetictube1ml", SYNTHETIC_LIST)
    assert result.value == "Synthetic Tube 1 mL"


def test_no_match_keeps_value_and_gives_not_in_lookup() -> None:
    """A value with no match stays as written and is noted as NOT_IN_LOOKUP."""
    result = match_lookup_value("2–8 °C synthetic", SYNTHETIC_LIST)
    assert result.value == "2–8 °C synthetic"
    assert result.note == TransformNote(
        code="NOT_IN_LOOKUP", original="2–8 °C synthetic", value="2–8 °C synthetic"
    )


def test_two_normalized_matches_are_not_guessed() -> None:
    """When two list values match after normalizing, none is picked: NOT_IN_LOOKUP."""
    ambiguous_list = ["Synthetic Bottle 1 mL", "synthetic bottle 1ml"]
    result = match_lookup_value("SYNTHETIC BOTTLE °1ML", ambiguous_list)
    assert result.value == "SYNTHETIC BOTTLE °1ML"
    assert result.note is not None
    assert result.note.code == "NOT_IN_LOOKUP"


def test_case_insensitive_match_wins_over_normalized_matches() -> None:
    """One case-insensitive match is used even when a normalized match would be ambiguous."""
    case_list = ["Synthetic Bottle 1 mL", "synthetic bottle 1ml"]
    result = match_lookup_value("SYNTHETIC BOTTLE 1 ML", case_list)
    assert result.value == "Synthetic Bottle 1 mL"


def test_boolean_y_and_n_are_kept() -> None:
    """Y and N are already loader values."""
    assert match_boolean_value("Y").note is None
    assert match_boolean_value("N").value == "N"


def test_boolean_lower_case_is_format_corrected() -> None:
    """Lower-case y becomes Y with a FORMAT_CORRECTED note."""
    result = match_boolean_value("y")
    assert result.value == "Y"
    assert result.note is not None
    assert result.note.code == "FORMAT_CORRECTED"


def test_boolean_word_is_not_guessed() -> None:
    """A word such as "Yes" is not turned into Y; it is kept and noted as NOT_IN_LOOKUP."""
    result = match_boolean_value("Yes")
    assert result.value == "Yes"
    assert result.note is not None
    assert result.note.code == "NOT_IN_LOOKUP"
