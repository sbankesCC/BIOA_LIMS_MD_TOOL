"""Transformation (ARCHITECTURE §4.7): writes each field's `output` section from its extraction.

Code only, no LLM. Cleans text, joins multi-value fields, matches lookup lists, reads numbers and
fills defaults into empty fields. It never touches a user's value and creates no issues: its
notes go into `output.changes`, and validation turns the coded ones into issues.
"""

from collections.abc import Sequence

from pydantic import BaseModel

from app.config.field_rules import FieldRule, FieldRules
from app.config.lookup_lists import LookupLists
from app.contracts.extraction import ExtractedField, ExtractedValue
from app.contracts.record import FieldOutput, Origin, StoredField, StoredRecord
from app.transform.cleaning import clean_text
from app.transform.lookup_matching import match_boolean_value, match_lookup_value
from app.transform.notes import TransformNote
from app.transform.numbers import read_number

# Origins of values a person set: transformation never changes these
USER_ORIGINS: tuple[Origin, ...] = ("user_edited", "fixed")

# Field types whose values are read as numbers
NUMBER_TYPES = ("decimal", "integer")


class TransformedValue(BaseModel):
    """A loader-ready value (None when empty) and the notes on how it was made."""

    value: str | None
    changes: list[str] = []


def transform_records(
    records: Sequence[StoredRecord], field_rules: FieldRules, lookup_lists: LookupLists
) -> list[StoredRecord]:
    """Return the records with every field's output section rebuilt from its extraction."""
    return [transform_record(record, field_rules, lookup_lists) for record in records]


def transform_record(
    record: StoredRecord, field_rules: FieldRules, lookup_lists: LookupLists
) -> StoredRecord:
    """Return a copy of the record with each loader field's output written by transformation."""
    fields = dict(record.fields)
    # Every loader field gets an entry; keys the rules do not know are left for validation
    for rule in field_rules.fields:
        fields[rule.key] = transform_field(rule, record.fields.get(rule.key), lookup_lists)
    return record.model_copy(update={"fields": fields})


def transform_field(
    rule: FieldRule, stored: StoredField | None, lookup_lists: LookupLists
) -> StoredField:
    """Return the field with a new output section, unless a person already set its value."""
    if stored is not None and stored.output.origin in USER_ORIGINS:
        return stored
    extraction = stored.extraction if stored is not None else None
    output = build_field_output(rule, extraction, lookup_lists)
    # Only the output section changes; extraction, verification and issues stay as they were
    if stored is None:
        return StoredField(output=output)
    return stored.model_copy(update={"output": output})


def build_field_output(
    rule: FieldRule, extraction: ExtractedField | None, lookup_lists: LookupLists
) -> FieldOutput:
    """Build a field's output from its role, its extraction and its default."""
    # Fields the tool does not fill are exported blank
    if rule.role == "blank_for_now" or rule.role == "system":
        return FieldOutput(value=None, origin=rule.role)
    # A found value is transformed; a conflict waits for the user's choice
    if extraction is not None and extraction.status == "found" and extraction.value is not None:
        transformed = transform_value(rule, extraction.value, lookup_lists)
        if transformed.value is not None:
            return FieldOutput(
                value=transformed.value, origin="extracted", changes=transformed.changes
            )
    is_conflicting = extraction is not None and extraction.status == "conflicting"
    # The configured default fills a field that is still empty and not in conflict
    if rule.default is not None and not is_conflicting:
        note = TransformNote(code="DEFAULT_APPLIED", value=rule.default)
        return FieldOutput(value=rule.default, origin="default", changes=[note.to_text()])
    return FieldOutput(value=None, origin="extracted")


def transform_value(
    rule: FieldRule, raw_value: ExtractedValue, lookup_lists: LookupLists
) -> TransformedValue:
    """Clean a value as written, then format it by the field's lookup list or type."""
    cleaned = join_values(rule, raw_value)
    if cleaned.value is None:
        return cleaned
    changes = list(cleaned.changes)
    # Lookup fields are matched to their list; booleans to Y/N; number fields read as numbers
    value = cleaned.value
    note: TransformNote | None = None
    if rule.lookup_sheet is not None:
        allowed = lookup_lists.sheets.get(rule.lookup_sheet, [])
        matched = match_lookup_value(value, allowed)
        value, note = matched.value, matched.note
    elif rule.type == "boolean":
        matched = match_boolean_value(value)
        value, note = matched.value, matched.note
    elif rule.type in NUMBER_TYPES:
        number = read_number(value)
        value, note = number.value, number.note
    if note is not None:
        changes.append(note.to_text())
    return TransformedValue(value=value, changes=changes)


def join_values(rule: FieldRule, raw_value: ExtractedValue) -> TransformedValue:
    """Clean each value; a multi-value field's values are joined with its separator."""
    parts = [raw_value] if isinstance(raw_value, str) else raw_value
    changes: list[str] = []
    cleaned_parts: list[str] = []
    # Clean each part, keep each clean-up note once, and drop parts that end up empty
    for part in parts:
        cleaned = clean_text(part)
        changes.extend(note for note in cleaned.notes if note not in changes)
        if cleaned.value:
            cleaned_parts.append(cleaned.value)
    if not cleaned_parts:
        return TransformedValue(value=None, changes=changes)
    separator = rule.separator if rule.multi_value and rule.separator else " "
    return TransformedValue(value=separator.join(cleaned_parts), changes=changes)
