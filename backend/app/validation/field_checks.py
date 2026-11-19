"""Field checks: required, conflicts, lookup, type, length and disallowed characters.

Every rule comes from `business_rules.md` and the run's lookup lists. Only fields with role
`extracted` are checked; `blank_for_now` and `system` fields are exported blank and skipped.
"""

import re
import unicodedata

from pydantic import JsonValue

from app.config.business_rules import DisallowedCharacters, FieldDefinition
from app.config.lookup_lists import LookupLists
from app.contracts.record import StoredField
from app.normalization.lookup_matching import BOOLEAN_VALUES
from app.normalization.notes import find_transform_notes
from app.normalization.numbers import PLAIN_NUMBER
from app.validation import codes
from app.validation.issues import IssueDraft

# Notes that explain why a value is blank: the value was found, but could not be used as it is
BLANK_EXPLAINING_CODES = (
    codes.NOT_IN_LOOKUP,
    codes.REVIEWER_CHOICE_NEEDED,
    codes.NOT_A_CONCENTRATION,
    codes.DERIVED_VALUE_MISSING,
)

# A whole number for integer fields: optional sign, digits only
PLAIN_INTEGER = re.compile(r"[-+]?\d+")

# Unicode blocks of Greek letters: Greek and Coptic, and Greek Extended
GREEK_RANGES = ((0x0370, 0x03FF), (0x1F00, 0x1FFF))

# Unicode category of control characters (tabs, line breaks, other C0/C1 codes)
CONTROL_CATEGORY = "Cc"


def is_checked_field(rule: FieldDefinition) -> bool:
    """Return True for fields validation checks: the ones the model extracts."""
    return rule.is_extracted


def check_field(
    record_id: str, rule: FieldDefinition, stored: StoredField, lookup_lists: LookupLists
) -> list[IssueDraft]:
    """Return the problems with one field's output value."""
    value = stored.output.value
    if value is None or value == "":
        return check_empty_field(record_id, rule, stored)
    return check_filled_value(record_id, rule, value, lookup_lists, stored)


def check_empty_field(
    record_id: str, rule: FieldDefinition, stored: StoredField
) -> list[IssueDraft]:
    """Return the problem with an empty field: an open conflict, a missing value, or none."""
    code = find_empty_field_code(rule, stored)
    if code is None:
        return []
    return [IssueDraft(code=code, record_id=record_id, field=rule.key)]


def find_empty_field_code(rule: FieldDefinition, stored: StoredField) -> str | None:
    """Return the issue code for an empty field, or None for a conditional field."""
    # A conflict nobody has resolved yet says more than "missing"
    extraction = stored.extraction
    if extraction is not None and extraction.status == "conflicting":
        return codes.CONFLICT_UNRESOLVED
    # The name has its own issue (NAME_NOT_SET); a blank a note explains is not "not found"
    if rule.is_record_name or is_blank_explained(stored):
        return None
    if rule.requirement == "required":
        return codes.REQUIRED_MISSING
    # Conditional fields are checked by their condition groups instead
    if rule.requirement == "optional":
        return codes.OPTIONAL_NOT_FOUND
    return None


def is_blank_explained(stored: StoredField) -> bool:
    """Return True if a coded note says why the value is blank (not that it was not found)."""
    notes = find_transform_notes(stored.output.changes)
    return any(note.code in BLANK_EXPLAINING_CODES for note in notes)


def check_filled_value(
    record_id: str,
    rule: FieldDefinition,
    value: str,
    lookup_lists: LookupLists,
    stored: StoredField | None = None,
) -> list[IssueDraft]:
    """Return every rule a filled value breaks: list, type, length and characters."""
    found_codes: list[str] = []
    message_values: dict[str, str] = {}
    # List fields must hold a value of their lookup list; booleans must be Y or N
    if rule.lookup_sheet is not None:
        if value not in lookup_lists.sheets.get(rule.lookup_sheet, []):
            found_codes.append(codes.NOT_IN_LOOKUP)
    elif rule.type == "boolean" and value not in BOOLEAN_VALUES:
        found_codes.append(codes.NOT_IN_LOOKUP)
    if not is_right_type(rule, value):
        found_codes.append(codes.WRONG_TYPE)
    # The length limit is applied literally, as the workbook gives it
    if rule.max_length is not None and len(value) > rule.max_length:
        found_codes.append(codes.TOO_LONG)
        message_values["max_length"] = str(rule.max_length)
    if has_disallowed_characters(value, rule.disallowed_characters):
        found_codes.append(codes.INVALID_CHARACTERS)
    return [
        IssueDraft(
            code=code,
            record_id=record_id,
            field=rule.key,
            value=value,
            message_values=message_values if code == codes.TOO_LONG else {},
            details=find_suggestion_details(code, stored),
        )
        for code in found_codes
    ]


def find_suggestion_details(code: str, stored: StoredField | None) -> dict[str, JsonValue]:
    """Return the suggestion NOT_IN_LOOKUP carries, or why there is none (CONTRACTS §6)."""
    if code != codes.NOT_IN_LOOKUP or stored is None:
        return {}
    if stored.suggestion is not None:
        return {"suggestion": stored.suggestion.model_dump(mode="json")}
    if stored.no_suggestion_reason is not None:
        return {"no_suggestion_reason": stored.no_suggestion_reason}
    return {}


def is_right_type(rule: FieldDefinition, value: str) -> bool:
    """Return True if the value fits the field's type; text and boolean always fit here."""
    if rule.type == "decimal":
        return PLAIN_NUMBER.fullmatch(value) is not None
    if rule.type == "integer":
        return PLAIN_INTEGER.fullmatch(value) is not None
    return True


def has_disallowed_characters(value: str, disallowed: list[DisallowedCharacters]) -> bool:
    """Return True if the value holds a character of any disallowed kind."""
    for character in value:
        if "greek_letters" in disallowed and is_greek_letter(character):
            return True
        if "control_characters" in disallowed and is_control_character(character):
            return True
    return False


def is_greek_letter(character: str) -> bool:
    """Return True for a character in the Greek Unicode blocks (such as α or µ written as μ)."""
    code_point = ord(character)
    return any(start <= code_point <= end for start, end in GREEK_RANGES)


def is_control_character(character: str) -> bool:
    """Return True for a control character (tab, line break, other control codes)."""
    return unicodedata.category(character) == CONTROL_CATEGORY
