"""Number reading tests: plain numbers kept, one number read from text, the rest kept as written."""

import pytest

from app.transform.notes import TransformNote
from app.transform.numbers import read_number


@pytest.mark.parametrize("value", ["10", "2.50", "-20", "0"])
def test_plain_number_is_kept_without_note(value: str) -> None:
    """A value that is already a plain number is not changed."""
    result = read_number(value)
    assert result.value == value
    assert result.note is None


def test_exponent_with_unit_is_read_as_plain_number() -> None:
    """The CONTRACTS example: "1e4 cps/uL" gives 10000, noted as NUMBER_READ_FROM_TEXT."""
    result = read_number("1e4 cps/uL")
    assert result.value == "10000"
    assert result.note == TransformNote(
        code="NUMBER_READ_FROM_TEXT", original="1e4 cps/uL", value="10000"
    )


@pytest.mark.parametrize(
    ("text", "number"),
    [
        ("100 uM", "100"),
        ("1,000 cells", "1000"),
        (".5 synthetic units", "0.5"),
        ("1.5e-3 M", "0.0015"),
        ("-20 degrees", "-20"),
        ("approx. 15", "15"),
    ],
)
def test_single_number_in_text_is_read(text: str, number: str) -> None:
    """Text holding exactly one number gives that number as plain digits."""
    result = read_number(text)
    assert result.value == number
    assert result.note is not None
    assert result.note.code == "NUMBER_READ_FROM_TEXT"


@pytest.mark.parametrize("text", ["2-8", "1 x 10^4", "one vial", "see table", "-2-8"])
def test_unreadable_number_is_kept_as_written(text: str) -> None:
    """No number, or several numbers, keeps the text as written for validation (WRONG_TYPE)."""
    result = read_number(text)
    assert result.value == text
    assert result.note is None
