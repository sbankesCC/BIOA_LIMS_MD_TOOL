"""Transform note tests: coded notes round-trip through text; plain clean-up notes are skipped."""

from app.transform.notes import (
    TRIMMED_WHITESPACE,
    TransformNote,
    find_transform_notes,
    parse_transform_note,
)


def test_coded_note_round_trips_through_text() -> None:
    """A note written to `output.changes` reads back as the same note."""
    note = TransformNote(code="FORMAT_CORRECTED", original='synthetic: ° "a"', value="Synthetic")
    assert parse_transform_note(note.to_text()) == note


def test_note_text_starts_with_its_code() -> None:
    """The stored text starts with the issue code, so it is readable in the audit file."""
    note = TransformNote(code="DEFAULT_APPLIED", value="synthetic default")
    assert note.to_text().startswith("DEFAULT_APPLIED: ")


def test_plain_and_unknown_notes_are_not_coded() -> None:
    """Clean-up notes, unknown codes and broken JSON give no coded note."""
    assert parse_transform_note(TRIMMED_WHITESPACE) is None
    assert parse_transform_note('TOO_LONG: {"original": null, "value": null}') is None
    assert parse_transform_note("FORMAT_CORRECTED: {broken}") is None


def test_find_transform_notes_keeps_only_coded_notes_in_order() -> None:
    """Only coded notes are returned, in the order they were written."""
    first = TransformNote(code="NUMBER_READ_FROM_TEXT", original="1 synthetic", value="1")
    second = TransformNote(code="NOT_IN_LOOKUP", original="x y", value="x y")
    changes = [TRIMMED_WHITESPACE, first.to_text(), second.to_text()]
    assert find_transform_notes(changes) == [first, second]
