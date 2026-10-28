"""Transform notes: what transformation changed, stored as text in a field's `output.changes`.

Plain clean-up notes are short sentences ("trimmed whitespace"). Notes that validation turns into
issues start with an issue code: `CODE: {"original": ..., "value": ...}`.
"""

import json
import re
from typing import Literal, cast, get_args

from pydantic import BaseModel

# Issue codes transformation records as notes (defined in the client's issue catalogue)
TransformNoteCode = Literal[
    "FORMAT_CORRECTED", "NOT_IN_LOOKUP", "NUMBER_READ_FROM_TEXT", "DEFAULT_APPLIED"
]
NOTE_CODES: tuple[str, ...] = get_args(TransformNoteCode)

# Plain clean-up notes, written by cleaning.py
TRIMMED_WHITESPACE = "trimmed whitespace"
COLLAPSED_SPACES = "collapsed spaces"
REMOVED_CONTROL_CHARACTERS = "removed control characters"

# A coded note is the code, a colon and a space, then a JSON object
CODED_NOTE_PATTERN = re.compile(r"^([A-Z_]+): (\{.*\})$", re.DOTALL)


class TransformNote(BaseModel):
    """A change validation reports as an issue: the code, the value as written and the result."""

    code: TransformNoteCode
    original: str | None = None
    value: str | None = None

    def to_text(self) -> str:
        """Return the note as the text stored in `output.changes`."""
        details = {"original": self.original, "value": self.value}
        return f"{self.code}: {json.dumps(details, ensure_ascii=False)}"


def parse_transform_note(text: str) -> TransformNote | None:
    """Read a coded note back from `output.changes`; plain clean-up notes give None."""
    match = CODED_NOTE_PATTERN.match(text)
    if match is None or match.group(1) not in NOTE_CODES:
        return None
    # The JSON part was written by `to_text`, so anything else is not a coded note
    try:
        details = json.loads(match.group(2))
    except json.JSONDecodeError:
        return None
    if not isinstance(details, dict):
        return None
    details = cast(dict[str, object], details)
    return TransformNote(
        code=cast(TransformNoteCode, match.group(1)),
        original=read_optional_text(details, "original"),
        value=read_optional_text(details, "value"),
    )


def read_optional_text(details: dict[str, object], key: str) -> str | None:
    """Return a text entry of a note's details, or None if it is missing or not text."""
    entry = details.get(key)
    return entry if isinstance(entry, str) else None


def find_transform_notes(changes: list[str]) -> list[TransformNote]:
    """Return the coded notes among a field's changes, in order."""
    notes = [parse_transform_note(text) for text in changes]
    return [note for note in notes if note is not None]
