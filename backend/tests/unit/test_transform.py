"""Transformation tests: output sections built from extractions, defaults, roles and user values.

Field keys, lookup values and defaults are read from the client config, never written here.
"""

from collections.abc import Callable

from app.config.bundle import ConfigBundle
from app.config.field_rules import FieldRule, FieldRules
from app.contracts.extraction import Alternative, Evidence, ExtractedField, ExtractedValue
from app.contracts.record import FieldOutput, Origin, RecordExtraction, StoredField, StoredRecord
from app.transform.notes import COLLAPSED_SPACES, TRIMMED_WHITESPACE, find_transform_notes
from app.transform.transform import transform_record

EVIDENCE = Evidence(chunk_id="doc01-c001", quote="synthetic quote")


def find_rule(field_rules: FieldRules, is_wanted: Callable[[FieldRule], bool]) -> FieldRule:
    """Return the first extracted field rule that `is_wanted` accepts."""
    return next(rule for rule in field_rules.extracted_fields() if is_wanted(rule))


def found(value: ExtractedValue) -> ExtractedField:
    """Return a found extracted field with one evidence pair."""
    return ExtractedField(status="found", value=value, evidence=[EVIDENCE])


def make_record(
    field_rules: FieldRules, extractions: dict[str, ExtractedField] | None = None
) -> StoredRecord:
    """Build a synthetic stored record: every loader field, extracted ones not found by default."""
    extractions = extractions or {}
    fields: dict[str, StoredField] = {}
    for rule in field_rules.fields:
        extraction = None
        if rule.role == "extracted":
            extraction = extractions.get(rule.key, ExtractedField(status="not_found"))
        fields[rule.key] = StoredField(
            extraction=extraction, output=FieldOutput(origin="extracted")
        )
    return StoredRecord(
        record_id="rec_0001",
        found_in=["doc01-c001"],
        extraction=RecordExtraction(record_ref="R1", record_summary="synthetic record"),
        fields=fields,
    )


def transform_one(bundle: ConfigBundle, key: str, extraction: ExtractedField) -> FieldOutput:
    """Transform a record with one extracted field and return that field's output."""
    record = make_record(bundle.field_rules, {key: extraction})
    result = transform_record(record, bundle.field_rules, bundle.lookup_lists)
    return result.fields[key].output


def lookup_rule(bundle: ConfigBundle) -> FieldRule:
    """Return a lookup field with no default whose list has a value with a space in it."""
    sheets = bundle.lookup_lists.sheets
    return find_rule(
        bundle.field_rules,
        lambda rule: (
            rule.lookup_sheet is not None
            and rule.default is None
            and any(" " in value for value in sheets[rule.lookup_sheet])
        ),
    )


def spaced_value(bundle: ConfigBundle, rule: FieldRule) -> str:
    """Return the first value on the rule's lookup list that has a space in it."""
    assert rule.lookup_sheet is not None
    return next(value for value in bundle.lookup_lists.sheets[rule.lookup_sheet] if " " in value)


def test_found_text_value_is_cleaned(bundle: ConfigBundle) -> None:
    """A plain text field is trimmed and its spaces collapsed, with clean-up notes."""
    rule = find_rule(bundle.field_rules, lambda rule: rule.type == "text" and not rule.lookup_sheet)
    output = transform_one(bundle, rule.key, found("  synthetic   name "))
    assert output.value == "synthetic name"
    assert output.origin == "extracted"
    assert output.changes == [TRIMMED_WHITESPACE, COLLAPSED_SPACES]


def test_exact_lookup_value_is_kept(bundle: ConfigBundle) -> None:
    """A lookup value written exactly as on the list is kept with no changes."""
    rule = lookup_rule(bundle)
    value = spaced_value(bundle, rule)
    output = transform_one(bundle, rule.key, found(value))
    assert output.value == value
    assert output.changes == []


def test_lookup_value_in_other_case_is_format_corrected(bundle: ConfigBundle) -> None:
    """A lookup value in upper case is matched to the list's spelling with FORMAT_CORRECTED."""
    rule = lookup_rule(bundle)
    value = spaced_value(bundle, rule)
    output = transform_one(bundle, rule.key, found(value.upper()))
    assert output.value == value
    notes = find_transform_notes(output.changes)
    assert [(note.code, note.original, note.value) for note in notes] == [
        ("FORMAT_CORRECTED", value.upper(), value)
    ]


def test_lookup_value_with_degree_sign_and_spaces_is_matched(bundle: ConfigBundle) -> None:
    """A list value written with extra spaces and a degree sign still matches."""
    rule = lookup_rule(bundle)
    value = spaced_value(bundle, rule)
    written = value.replace(" ", " ° ", 1).lower()
    output = transform_one(bundle, rule.key, found(written))
    assert output.value == value
    assert find_transform_notes(output.changes)[0].code == "FORMAT_CORRECTED"


def test_unknown_lookup_value_is_kept_with_not_in_lookup(bundle: ConfigBundle) -> None:
    """A value with no list match stays as written and is noted as NOT_IN_LOOKUP."""
    rule = lookup_rule(bundle)
    output = transform_one(bundle, rule.key, found("Synthetic unlisted value"))
    assert output.value == "Synthetic unlisted value"
    assert output.origin == "extracted"
    assert find_transform_notes(output.changes)[0].code == "NOT_IN_LOOKUP"


def test_boolean_field_lower_case_becomes_upper_case(bundle: ConfigBundle) -> None:
    """A boolean field written as "n" is exported as N."""
    rule = find_rule(bundle.field_rules, lambda rule: rule.type == "boolean")
    output = transform_one(bundle, rule.key, found("n"))
    assert output.value == "N"
    assert find_transform_notes(output.changes)[0].code == "FORMAT_CORRECTED"


def test_number_field_reads_number_from_text(bundle: ConfigBundle) -> None:
    """A decimal field written with a unit gives the number, noted as NUMBER_READ_FROM_TEXT."""
    rule = find_rule(bundle.field_rules, lambda rule: rule.type == "decimal")
    output = transform_one(bundle, rule.key, found("1e4 cps/uL"))
    assert output.value == "10000"
    notes = find_transform_notes(output.changes)
    assert [(note.code, note.original) for note in notes] == [
        ("NUMBER_READ_FROM_TEXT", "1e4 cps/uL")
    ]


def test_unreadable_number_is_kept_as_written(bundle: ConfigBundle) -> None:
    """A number field with no single number keeps the text, for validation to flag."""
    rule = find_rule(bundle.field_rules, lambda rule: rule.type == "integer")
    output = transform_one(bundle, rule.key, found("several"))
    assert output.value == "several"
    assert output.changes == []


def test_multi_value_field_is_joined_with_separator(bundle: ConfigBundle) -> None:
    """A multi-value field's values are cleaned and joined with the configured separator."""
    rule = find_rule(bundle.field_rules, lambda rule: rule.multi_value)
    assert rule.separator is not None
    output = transform_one(bundle, rule.key, found(["SYN-001 ", "SYN-002"]))
    assert output.value == rule.separator.join(["SYN-001", "SYN-002"])
    assert output.changes == [TRIMMED_WHITESPACE]


def test_default_is_applied_to_not_found_field(bundle: ConfigBundle) -> None:
    """A not-found field with a default gets it, with origin default and DEFAULT_APPLIED."""
    rule = find_rule(bundle.field_rules, lambda rule: rule.default is not None)
    output = transform_one(bundle, rule.key, ExtractedField(status="not_found"))
    assert output.value == rule.default
    assert output.origin == "default"
    notes = find_transform_notes(output.changes)
    assert [(note.code, note.value) for note in notes] == [("DEFAULT_APPLIED", rule.default)]


def test_default_does_not_replace_found_value(bundle: ConfigBundle) -> None:
    """A field with a default keeps the value found in the documents."""
    rule = find_rule(bundle.field_rules, lambda rule: rule.default is not None)
    assert rule.lookup_sheet is not None
    other_value = next(
        value for value in bundle.lookup_lists.sheets[rule.lookup_sheet] if value != rule.default
    )
    output = transform_one(bundle, rule.key, found(other_value))
    assert output.value == other_value
    assert output.origin == "extracted"


def test_default_is_not_applied_to_conflicting_field(bundle: ConfigBundle) -> None:
    """A conflicting field stays empty for the user's choice, even when it has a default."""
    rule = find_rule(bundle.field_rules, lambda rule: rule.default is not None)
    conflict = ExtractedField(
        status="conflicting",
        alternatives=[
            Alternative(value="synthetic one", evidence=[EVIDENCE]),
            Alternative(value="synthetic two", evidence=[EVIDENCE]),
        ],
        warning="synthetic conflict",
    )
    output = transform_one(bundle, rule.key, conflict)
    assert output.value is None
    assert output.origin == "extracted"
    assert output.changes == []


def test_container_tracking_default_is_applied_literally(bundle: ConfigBundle) -> None:
    """A default longer than its field's limit is applied as written; validation flags TOO_LONG."""
    rule = find_rule(
        bundle.field_rules,
        lambda rule: (
            rule.default is not None
            and rule.max_length is not None
            and len(rule.default) > rule.max_length
        ),
    )
    output = transform_one(bundle, rule.key, ExtractedField(status="not_found"))
    assert output.value == rule.default
    assert output.origin == "default"


def test_not_found_field_without_default_stays_empty(bundle: ConfigBundle) -> None:
    """Nothing is invented: a not-found field with no default has no value."""
    rule = find_rule(bundle.field_rules, lambda rule: rule.default is None)
    output = transform_one(bundle, rule.key, ExtractedField(status="not_found"))
    assert output.value is None
    assert output.changes == []


def test_blank_for_now_and_system_fields_are_empty(bundle: ConfigBundle) -> None:
    """Fields the tool does not fill are empty, with their role as origin."""
    record = transform_record(
        make_record(bundle.field_rules), bundle.field_rules, bundle.lookup_lists
    )
    for rule in bundle.field_rules.fields:
        if rule.role in ("blank_for_now", "system"):
            assert record.fields[rule.key].output == FieldOutput(value=None, origin=rule.role)


def test_transformation_never_overwrites_user_value(bundle: ConfigBundle) -> None:
    """A value a person set (user_edited or fixed) is kept exactly, output section and all."""
    rule = find_rule(bundle.field_rules, lambda rule: rule.default is not None)
    record = make_record(bundle.field_rules)
    user_origins: tuple[Origin, ...] = ("user_edited", "fixed")
    for origin in user_origins:
        user_output = FieldOutput(value="synthetic user value", origin=origin, changes=["by user"])
        field = record.fields[rule.key].model_copy(update={"output": user_output})
        user_record = record.model_copy(update={"fields": {**record.fields, rule.key: field}})
        result = transform_record(user_record, bundle.field_rules, bundle.lookup_lists)
        assert result.fields[rule.key].output == user_output


def test_transformation_writes_only_the_output_section(bundle: ConfigBundle) -> None:
    """Extraction, verification and issue IDs of every field are left as they were."""
    rule = lookup_rule(bundle)
    record = make_record(bundle.field_rules, {rule.key: found("synthetic value")})
    result = transform_record(record, bundle.field_rules, bundle.lookup_lists)
    for key, field in result.fields.items():
        before = record.fields[key]
        assert field.extraction == before.extraction
        assert field.verification == before.verification
        assert field.issue_ids == before.issue_ids
    assert result.model_copy(update={"fields": record.fields}) == record


def test_transformation_is_repeatable(bundle: ConfigBundle) -> None:
    """Transforming an already transformed record gives the same record."""
    rule = lookup_rule(bundle)
    record = make_record(bundle.field_rules, {rule.key: found(" synthetic value ")})
    once = transform_record(record, bundle.field_rules, bundle.lookup_lists)
    twice = transform_record(once, bundle.field_rules, bundle.lookup_lists)
    assert twice == once
