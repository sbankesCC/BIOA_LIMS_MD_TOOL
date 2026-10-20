"""Status rules (CONTRACTS §2): code checks on every parsed extraction response.

Returns the violations found and never raises; the extraction node retries on a violation.
Messages name records, fields and chunk IDs only, never values, so they are safe to log.
"""

from typing import Literal

from pydantic import BaseModel

from app.config.field_rules import FieldRule, FieldRules
from app.contracts.extraction import (
    Evidence,
    ExcludedItem,
    ExtractedField,
    ExtractedRecord,
    ExtractedValue,
    ExtractionOutput,
)

ViolationRule = Literal[
    "duplicate_record_ref",
    "found_in_empty",
    "unknown_chunk_id",
    "field_missing",
    "field_not_extracted",
    "value_wrong_shape",
    "found_without_value",
    "found_without_evidence",
    "found_with_alternatives",
    "conflicting_with_value",
    "conflicting_with_evidence",
    "conflicting_without_two_alternatives",
    "alternative_without_value",
    "alternative_without_evidence",
    "conflicting_without_warning",
    "not_found_with_value",
    "not_found_with_evidence",
    "not_found_with_alternatives",
]


class StatusViolation(BaseModel):
    """One broken rule: which rule, where (record and field, when known) and a plain message."""

    rule: ViolationRule
    record_ref: str | None
    field: str | None
    message: str


def find_status_violations(
    output: ExtractionOutput, field_rules: FieldRules, chunk_ids: set[str]
) -> list[StatusViolation]:
    """Check an extraction response against the status table, field set and known chunk IDs."""
    violations = find_duplicate_record_refs(output.records)
    for record in output.records:
        violations.extend(find_record_violations(record, field_rules, chunk_ids))
    for item in output.excluded_items:
        violations.extend(find_excluded_item_violations(item, chunk_ids))
    return violations


def find_duplicate_record_refs(records: list[ExtractedRecord]) -> list[StatusViolation]:
    """Report a record_ref used by more than one record (code maps each ref to one ID)."""
    violations: list[StatusViolation] = []
    seen_refs: set[str] = set()
    for record in records:
        if record.record_ref in seen_refs:
            message = f"record_ref {record.record_ref} is used by more than one record."
            violation = make_violation("duplicate_record_ref", record.record_ref, None, message)
            violations.append(violation)
        seen_refs.add(record.record_ref)
    return violations


def find_record_violations(
    record: ExtractedRecord, field_rules: FieldRules, chunk_ids: set[str]
) -> list[StatusViolation]:
    """Check one record: found_in, its chunk IDs, the field set, then each field."""
    ref = record.record_ref
    violations: list[StatusViolation] = []
    # Every record must say where it was found
    if not record.found_in:
        message = f"Record {ref} has no found_in chunk IDs; at least one is required."
        violations.append(make_violation("found_in_empty", ref, None, message))
    violations.extend(find_unknown_chunk_ids(record.found_in, ref, None, chunk_ids))
    violations.extend(find_field_set_violations(record, field_rules))
    # Each known extracted field is checked on its own; unknown keys were reported above
    rules_by_key = {field.key: field for field in field_rules.extracted_fields()}
    for key, field in record.fields.items():
        rule = rules_by_key.get(key)
        if rule is not None:
            violations.extend(find_field_violations(ref, rule, field, chunk_ids))
    return violations


def find_field_set_violations(
    record: ExtractedRecord, field_rules: FieldRules
) -> list[StatusViolation]:
    """Report extracted fields the record lacks and keys that are not extracted fields."""
    ref = record.record_ref
    extracted_keys = [field.key for field in field_rules.extracted_fields()]
    violations: list[StatusViolation] = []
    for key in extracted_keys:
        if key not in record.fields:
            message = f"Record {ref} is missing field '{key}'; every extracted field is required."
            violations.append(make_violation("field_missing", ref, key, message))
    for key in record.fields:
        if key not in extracted_keys:
            message = f"Record {ref} returns field '{key}', which is not an extracted field."
            violations.append(make_violation("field_not_extracted", ref, key, message))
    return violations


def find_field_violations(
    ref: str, rule: FieldRule, field: ExtractedField, chunk_ids: set[str]
) -> list[StatusViolation]:
    """Check one field: value shapes, the status table row, and every cited chunk ID."""
    violations = find_value_shape_violations(ref, rule, field)
    # Each status has its own row in the CONTRACTS §2 table
    if field.status == "found":
        violations.extend(find_found_violations(ref, rule.key, field))
    elif field.status == "conflicting":
        violations.extend(find_conflicting_violations(ref, rule.key, field))
    else:
        violations.extend(find_not_found_violations(ref, rule.key, field))
    # Evidence of the field and of its alternatives must cite real chunks
    cited = [evidence.chunk_id for evidence in all_evidence(field)]
    violations.extend(find_unknown_chunk_ids(cited, ref, rule.key, chunk_ids))
    return violations


def find_value_shape_violations(
    ref: str, rule: FieldRule, field: ExtractedField
) -> list[StatusViolation]:
    """Report a value or alternative that is a list for a single field, or text for a list field."""
    values: list[ExtractedValue] = [alternative.value for alternative in field.alternatives]
    if field.value is not None:
        values.append(field.value)
    expected_shape = "a list of strings" if rule.multi_value else "a single string"
    for value in values:
        if isinstance(value, list) != rule.multi_value:
            message = f"Record {ref}, field '{rule.key}': values must be {expected_shape}."
            return [make_violation("value_wrong_shape", ref, rule.key, message)]
    return []


def find_found_violations(ref: str, key: str, field: ExtractedField) -> list[StatusViolation]:
    """Check the `found` row: a value, at least one evidence pair, no alternatives."""
    violations: list[StatusViolation] = []
    where = f"Record {ref}, field '{key}' (found)"
    if not has_value(field.value):
        violations.append(make_violation("found_without_value", ref, key, f"{where} has no value."))
    if not field.evidence:
        message = f"{where} needs at least one evidence pair."
        violations.append(make_violation("found_without_evidence", ref, key, message))
    if field.alternatives:
        message = f"{where} must not have alternatives."
        violations.append(make_violation("found_with_alternatives", ref, key, message))
    return violations


def find_conflicting_violations(ref: str, key: str, field: ExtractedField) -> list[StatusViolation]:
    """Check the `conflicting` row: no value or evidence, two or more alternatives, a warning."""
    violations: list[StatusViolation] = []
    where = f"Record {ref}, field '{key}' (conflicting)"
    if field.value is not None:
        message = f"{where} must have a null value."
        violations.append(make_violation("conflicting_with_value", ref, key, message))
    if field.evidence:
        message = f"{where} must keep its evidence in the alternatives."
        violations.append(make_violation("conflicting_with_evidence", ref, key, message))
    if len(field.alternatives) < 2:
        message = f"{where} needs at least two alternatives."
        violations.append(make_violation("conflicting_without_two_alternatives", ref, key, message))
    violations.extend(find_alternative_violations(ref, key, field))
    if not has_text(field.warning):
        message = f"{where} needs a warning that describes the conflict."
        violations.append(make_violation("conflicting_without_warning", ref, key, message))
    return violations


def find_alternative_violations(ref: str, key: str, field: ExtractedField) -> list[StatusViolation]:
    """Check each alternative of a conflicting field has a value and evidence."""
    violations: list[StatusViolation] = []
    for index, alternative in enumerate(field.alternatives):
        where = f"Record {ref}, field '{key}', alternative {index}"
        if not has_value(alternative.value):
            message = f"{where} has no value."
            violations.append(make_violation("alternative_without_value", ref, key, message))
        if not alternative.evidence:
            message = f"{where} needs at least one evidence pair."
            violations.append(make_violation("alternative_without_evidence", ref, key, message))
    return violations


def find_not_found_violations(ref: str, key: str, field: ExtractedField) -> list[StatusViolation]:
    """Check the `not_found` row: no value, no evidence, no alternatives."""
    violations: list[StatusViolation] = []
    where = f"Record {ref}, field '{key}' (not_found)"
    if field.value is not None:
        message = f"{where} must have a null value."
        violations.append(make_violation("not_found_with_value", ref, key, message))
    if field.evidence:
        message = f"{where} must have no evidence."
        violations.append(make_violation("not_found_with_evidence", ref, key, message))
    if field.alternatives:
        message = f"{where} must have no alternatives."
        violations.append(make_violation("not_found_with_alternatives", ref, key, message))
    return violations


def find_excluded_item_violations(item: ExcludedItem, chunk_ids: set[str]) -> list[StatusViolation]:
    """Check an excluded item cites only known chunks."""
    return find_unknown_chunk_ids(item.chunk_ids, None, None, chunk_ids)


def find_unknown_chunk_ids(
    cited: list[str], ref: str | None, key: str | None, chunk_ids: set[str]
) -> list[StatusViolation]:
    """Report each cited chunk ID that is not a chunk of this run (once per ID)."""
    violations: list[StatusViolation] = []
    for chunk_id in sorted(set(cited) - chunk_ids):
        place = f"Record {ref}" if ref is not None else "An excluded item"
        if key is not None:
            place += f", field '{key}'"
        message = f"{place} cites chunk {chunk_id}, which does not exist."
        violations.append(make_violation("unknown_chunk_id", ref, key, message))
    return violations


def all_evidence(field: ExtractedField) -> list[Evidence]:
    """Return the field's evidence plus the evidence of every alternative."""
    evidence = list(field.evidence)
    for alternative in field.alternatives:
        evidence.extend(alternative.evidence)
    return evidence


def has_value(value: ExtractedValue | None) -> bool:
    """Tell whether a value is given: non-blank text, or a non-empty list of non-blank text."""
    if value is None:
        return False
    if isinstance(value, str):
        return has_text(value)
    return len(value) > 0 and all(has_text(item) for item in value)


def has_text(text: str | None) -> bool:
    """Tell whether a string holds something other than whitespace."""
    return text is not None and text.strip() != ""


def make_violation(
    rule: ViolationRule, ref: str | None, key: str | None, message: str
) -> StatusViolation:
    """Build one violation."""
    return StatusViolation(rule=rule, record_ref=ref, field=key, message=message)
