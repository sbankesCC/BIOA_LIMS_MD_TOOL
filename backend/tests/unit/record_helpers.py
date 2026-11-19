"""Shared helpers for Normalization and Assembly tests: synthetic records and table lookups.

Field keys, lookup values and table cells are read from the client config, never written here.
"""

from collections.abc import Callable

from app.config.bundle import ConfigBundle
from app.config.business_rules import BusinessRules, FieldDefinition, RuleTable
from app.contracts.extraction import Evidence, ExtractedField, ExtractedValue
from app.contracts.record import (
    FieldOutput,
    RecordExtraction,
    StoredContextAttribute,
    StoredField,
    StoredRecord,
)

EVIDENCE = Evidence(chunk_id="doc01-c001", quote="synthetic quote")
TRANSLATION_HEADING = "Translation table"


def find_rule(
    business_rules: BusinessRules, is_wanted: Callable[[FieldDefinition], bool]
) -> FieldDefinition:
    """Return the first extracted field definition that `is_wanted` accepts."""
    return next(rule for rule in business_rules.extracted_fields() if is_wanted(rule))


def found(value: ExtractedValue) -> ExtractedField:
    """Return a found extracted field with one evidence pair."""
    return ExtractedField(status="found", value=value, evidence=[EVIDENCE])


def make_record(
    business_rules: BusinessRules,
    extractions: dict[str, ExtractedField] | None = None,
    context: dict[str, ExtractedField] | None = None,
) -> StoredRecord:
    """Build a synthetic stored record: every loader field, extracted ones not found by default."""
    extractions = extractions or {}
    fields: dict[str, StoredField] = {}
    for rule in business_rules.fields:
        extraction = None
        if rule.is_extracted:
            extraction = extractions.get(rule.key, ExtractedField(status="not_found"))
        fields[rule.key] = StoredField(
            extraction=extraction, output=FieldOutput(origin="extracted")
        )
    context = context or {}
    attributes = {
        attribute.key: StoredContextAttribute(
            extraction=context.get(attribute.key, ExtractedField(status="not_found"))
        )
        for attribute in business_rules.context_fields()
    }
    return StoredRecord(
        record_id="rec_0001",
        found_in=["doc01-c001"],
        extraction=RecordExtraction(record_ref="R1", record_summary="synthetic record"),
        context=attributes,
        fields=fields,
    )


def with_output(record: StoredRecord, key: str, output: FieldOutput) -> StoredRecord:
    """Return the record with one field's output replaced."""
    field = record.fields[key].model_copy(update={"output": output})
    return record.model_copy(update={"fields": {**record.fields, key: field}})


def find_field_table(bundle: ConfigBundle, heading: str) -> tuple[FieldDefinition, RuleTable]:
    """Return the first field that owns a table with this heading, and the table."""
    for rule in bundle.business_rules.fields:
        for table in rule.tables:
            if table.heading == heading:
                return rule, table
    raise AssertionError(f"No field has a table '{heading}'.")


def find_business_table(business_rules: BusinessRules, heading: str) -> RuleTable:
    """Return a table of the business rules section by heading."""
    return next(table for table in business_rules.business.tables if table.heading == heading)


def find_lookup_rule(bundle: ConfigBundle, is_matching_allowed: bool) -> FieldDefinition:
    """Return an extracted lookup field with no default and no translation table."""
    return find_rule(
        bundle.business_rules,
        lambda rule: (
            rule.lookup_sheet is not None
            and rule.default is None
            and rule.matching_allowed == is_matching_allowed
            and not any(table.heading == TRANSLATION_HEADING for table in rule.tables)
            and any(" " in value for value in bundle.lookup_lists.sheets[rule.lookup_sheet])
        ),
    )


def spaced_value(bundle: ConfigBundle, rule: FieldDefinition) -> str:
    """Return the first value on the rule's lookup list that has a space in it."""
    assert rule.lookup_sheet is not None
    return next(value for value in bundle.lookup_lists.sheets[rule.lookup_sheet] if " " in value)
