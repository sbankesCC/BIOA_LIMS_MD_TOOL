"""Character translation (4.2): micro and Greek characters become ASCII (General rules table).

Applied to every text value before any other lookup, so names sort and filter on plain letters.
"""

from pydantic import BaseModel

from app.config.business_rules import BusinessRules, is_blank_cell

CHARACTER_TABLE_HEADING = "Character translation table"
CHARACTER_COLUMN = "Character"
REPLACEMENT_COLUMN = "Replace with"


class TranslatedText(BaseModel):
    """A value after character translation, and the note for what was replaced (if anything)."""

    value: str
    notes: list[str] = []


def build_character_map(business_rules: BusinessRules) -> dict[str, str]:
    """Return character → replacement from the active rows of the character translation table."""
    tables = [
        table for table in business_rules.general.tables if table.heading == CHARACTER_TABLE_HEADING
    ]
    if not tables:
        return {}
    return {
        row[CHARACTER_COLUMN]: row[REPLACEMENT_COLUMN]
        for row in tables[0].active_rows()
        if not is_blank_cell(row[CHARACTER_COLUMN])
    }


def translate_characters(text: str, character_map: dict[str, str]) -> TranslatedText:
    """Replace every mapped character; the note lists each character that was replaced."""
    replaced = [character for character in character_map if character in text]
    if not replaced:
        return TranslatedText(value=text)
    result = text
    for character in replaced:
        result = result.replace(character, character_map[character])
    return TranslatedText(value=result, notes=[f"translated characters: {''.join(replaced)}"])
