"""Text cleaning, the first transformation step: trim, collapse spaces, remove control characters.

Each clean-up applied is reported as a plain note for the field's `output.changes`.
"""

import re
import unicodedata

from pydantic import BaseModel

from app.transform.notes import COLLAPSED_SPACES, REMOVED_CONTROL_CHARACTERS, TRIMMED_WHITESPACE

# Any run of whitespace inside a value (tabs, line breaks, non-breaking spaces) becomes one space
WHITESPACE_RUN = re.compile(r"\s+")


class CleanedText(BaseModel):
    """A cleaned value and the clean-ups applied to it."""

    value: str
    notes: list[str] = []


def clean_text(text: str) -> CleanedText:
    """Remove control characters, trim the ends and collapse whitespace runs to one space."""
    notes: list[str] = []
    # Control characters that are not whitespace are dropped
    without_controls = remove_control_characters(text)
    if without_controls != text:
        notes.append(REMOVED_CONTROL_CHARACTERS)
    # Whitespace at either end is trimmed
    trimmed = without_controls.strip()
    if trimmed != without_controls:
        notes.append(TRIMMED_WHITESPACE)
    # Whitespace inside the value becomes single spaces
    collapsed = WHITESPACE_RUN.sub(" ", trimmed)
    if collapsed != trimmed:
        notes.append(COLLAPSED_SPACES)
    return CleanedText(value=collapsed, notes=notes)


def remove_control_characters(text: str) -> str:
    """Drop Unicode control characters (category Cc), keeping whitespace such as tabs."""
    return "".join(
        character
        for character in text
        if character.isspace() or unicodedata.category(character) != "Cc"
    )
