"""Normalization (ARCHITECTURE §4.7a): writes each extracted field's `normalization` section.

Steps, in order: clean the text, translate characters, apply the field's translation table,
match the lookup list, read numbers, classify concentrations, collect unresolved values for
Matching. A conflicting field is normalized once per alternative. Code only; it writes nothing
but `field.normalization` and never converts units.
"""

from collections.abc import Sequence

from pydantic import BaseModel

from app.config.business_rules import BusinessRules, FieldDefinition
from app.config.lookup_lists import LookupLists
from app.contracts.extraction import ExtractedField, ExtractedValue
from app.contracts.record import FieldNormalization, StoredField, StoredRecord
from app.normalization.characters import build_character_map, translate_characters
from app.normalization.cleaning import clean_text
from app.normalization.concentration import (
    classify_concentration,
    has_concentration_units,
    read_concentration_units,
)
from app.normalization.lookup_matching import MatchResult, match_boolean_value, match_lookup_value
from app.normalization.lookup_values import find_allowed_values
from app.normalization.matching_items import collect_unresolved_value
from app.normalization.notes import TransformNote
from app.normalization.numbers import read_number
from app.normalization.translation import find_translation

# The step name an exclusion row can name (Matching has its own)
NORMALIZATION_STEP = "Normalization"

# Field types whose values are read as numbers
NUMBER_TYPES = ("decimal", "integer")


class NormalizedValue(BaseModel):
    """One normalized value: the value (None when empty), notes, matching value and choices."""

    value: str | None = None
    notes: list[str] = []
    matching_value: str | None = None
    choices: list[str] = []


def normalize_records(
    records: Sequence[StoredRecord], business_rules: BusinessRules, lookup_lists: LookupLists
) -> list[StoredRecord]:
    """Return the records with every extracted field's normalization section rebuilt."""
    return [normalize_record(record, business_rules, lookup_lists) for record in records]


def normalize_record(
    record: StoredRecord, business_rules: BusinessRules, lookup_lists: LookupLists
) -> StoredRecord:
    """Return a copy of the record with each extracted field's normalization written."""
    fields = dict(record.fields)
    for rule in business_rules.extracted_fields():
        stored = record.fields.get(rule.key)
        if stored is not None:
            fields[rule.key] = normalize_field(rule, stored, business_rules, lookup_lists)
    return record.model_copy(update={"fields": fields})


def normalize_field(
    rule: FieldDefinition,
    stored: StoredField,
    business_rules: BusinessRules,
    lookup_lists: LookupLists,
) -> StoredField:
    """Return the field with a new normalization section; every other section stays as it was."""
    normalization = build_field_normalization(rule, stored.extraction, business_rules, lookup_lists)
    return stored.model_copy(update={"normalization": normalization})


def build_field_normalization(
    rule: FieldDefinition,
    extraction: ExtractedField | None,
    business_rules: BusinessRules,
    lookup_lists: LookupLists,
) -> FieldNormalization | None:
    """Normalize a found value, or each alternative of a conflict; None if there is nothing."""
    if extraction is None:
        return None
    if extraction.status == "conflicting":
        return normalize_alternatives(rule, extraction, business_rules, lookup_lists)
    if extraction.value is None:
        return None
    normalized = normalize_value(rule, extraction.value, business_rules, lookup_lists)
    return FieldNormalization(
        value=normalized.value,
        notes=normalized.notes,
        matching_value=normalized.matching_value,
        choices=normalized.choices,
    )


def normalize_alternatives(
    rule: FieldDefinition,
    extraction: ExtractedField,
    business_rules: BusinessRules,
    lookup_lists: LookupLists,
) -> FieldNormalization:
    """Normalize each alternative of a conflict; the notes are kept once each."""
    alternatives: list[str] = []
    notes: list[str] = []
    for alternative in extraction.alternatives:
        normalized = normalize_value(rule, alternative.value, business_rules, lookup_lists)
        # An alternative left for Matching or for a choice is compared by its text
        alternatives.append(normalized.value or normalized.matching_value or "")
        notes += [note for note in normalized.notes if note not in notes]
    return FieldNormalization(alternatives=alternatives, notes=notes)


def normalize_value(
    rule: FieldDefinition,
    raw_value: ExtractedValue,
    business_rules: BusinessRules,
    lookup_lists: LookupLists,
) -> NormalizedValue:
    """Run steps 1 to 7 on one extracted value."""
    notes: list[str] = []
    text = clean_and_join(rule, raw_value, build_character_map(business_rules), notes)
    if text is None:
        return NormalizedValue(notes=notes)
    # Step 3: the field's own translation table
    translation = find_translation(rule, text)
    if translation is not None and translation.value is None:
        return build_choice_result(text, translation.choices, notes)
    if translation is not None:
        notes.append(f"translated '{text}' ({translation.entry})")
        text = translation.value or text
    # Steps 4 to 7 depend on the field's kind
    allowed = find_allowed_values(rule, business_rules, lookup_lists, NORMALIZATION_STEP)
    return finish_value(rule, text, allowed, notes)


def clean_and_join(
    rule: FieldDefinition,
    raw_value: ExtractedValue,
    character_map: dict[str, str],
    notes: list[str],
) -> str | None:
    """Clean and translate each part (steps 1, 2), then join a multi-value field; None if empty."""
    parts = [raw_value] if isinstance(raw_value, str) else raw_value
    cleaned_parts: list[str] = []
    for part in parts:
        cleaned = clean_text(part)
        translated = translate_characters(cleaned.value, character_map)
        notes += [note for note in [*cleaned.notes, *translated.notes] if note not in notes]
        if translated.value:
            cleaned_parts.append(translated.value)
    if not cleaned_parts:
        return None
    separator = rule.separator if rule.multi_value and rule.separator else " "
    return separator.join(cleaned_parts)


def build_choice_result(text: str, choices: list[str], notes: list[str]) -> NormalizedValue:
    """Return the result for a "Reviewer chooses" row: no value, the choices and a note."""
    note = TransformNote(code="REVIEWER_CHOICE_NEEDED", original=text, value=None)
    return NormalizedValue(notes=[*notes, note.to_text()], choices=choices)


def finish_value(
    rule: FieldDefinition, text: str, allowed: list[str], notes: list[str]
) -> NormalizedValue:
    """Run steps 4 to 7: lookup match, number or concentration, value kept for Matching."""
    if rule.lookup_sheet is not None:
        return finish_lookup_value(rule, match_lookup_value(text, allowed), text, notes)
    if rule.type == "boolean":
        return finish_lookup_value(rule, match_boolean_value(text), text, notes)
    if has_concentration_units(rule):
        result = classify_concentration(text, read_concentration_units(rule))
        return NormalizedValue(value=result.value, notes=add_note(notes, result.note))
    if rule.type in NUMBER_TYPES:
        number = read_number(text)
        return NormalizedValue(value=number.value, notes=add_note(notes, number.note))
    return NormalizedValue(value=text, notes=notes)


def finish_lookup_value(
    rule: FieldDefinition, matched: MatchResult, text: str, notes: list[str]
) -> NormalizedValue:
    """Keep a matched value; send an unmatched one to Matching if the field allows it."""
    all_notes = add_note(notes, matched.note)
    if matched.note is None or matched.note.code != "NOT_IN_LOOKUP":
        return NormalizedValue(value=matched.value, notes=all_notes)
    unresolved = collect_unresolved_value(rule, text)
    return NormalizedValue(
        value=unresolved.value, notes=all_notes, matching_value=unresolved.matching_value
    )


def add_note(notes: list[str], note: TransformNote | None) -> list[str]:
    """Return the notes with one more coded note at the end (unchanged if there is none)."""
    return notes if note is None else [*notes, note.to_text()]
