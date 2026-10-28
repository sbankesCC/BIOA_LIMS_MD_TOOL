"""Status rule tests: one test per CONTRACTS §2 violation, on a synthetic extraction response.

Field keys are read from the client field rules, never written here.
"""

import pytest

from app.config.bundle import ConfigBundle
from app.config.field_rules import FieldRules
from app.contracts.extraction import (
    Alternative,
    Evidence,
    ExcludedItem,
    ExtractedField,
    ExtractedRecord,
    ExtractionOutput,
)
from app.status_rules import StatusViolation, find_status_violations

CHUNK_IDS = {"doc01-p01-c001", "doc01-p01-c002"}
EVIDENCE = Evidence(chunk_id="doc01-p01-c001", quote="synthetic quote")
OTHER_EVIDENCE = Evidence(chunk_id="doc01-p01-c002", quote="other synthetic quote")


def single_key(field_rules: FieldRules) -> str:
    """Return the key of the first extracted field that holds one value."""
    return next(field.key for field in field_rules.extracted_fields() if not field.multi_value)


def multi_key(field_rules: FieldRules) -> str:
    """Return the key of the first extracted multi_value field."""
    return next(field.key for field in field_rules.extracted_fields() if field.multi_value)


def build_valid_output(field_rules: FieldRules) -> ExtractionOutput:
    """Build a valid response: one record, one found single field, one found list field."""
    fields = {
        field.key: ExtractedField(status="not_found") for field in field_rules.extracted_fields()
    }
    fields[single_key(field_rules)] = ExtractedField(
        status="found", value="synthetic value", evidence=[EVIDENCE]
    )
    fields[multi_key(field_rules)] = ExtractedField(
        status="found", value=["SYN-1", "SYN-2"], evidence=[EVIDENCE]
    )
    record = ExtractedRecord(
        record_ref="R1",
        found_in=["doc01-p01-c001"],
        record_summary="synthetic record",
        fields=fields,
    )
    excluded = ExcludedItem(item="synthetic plate reader", reason="Instrument", chunk_ids=[])
    return ExtractionOutput(records=[record], excluded_items=[excluded])


def build_conflicting_field() -> ExtractedField:
    """Build a valid conflicting single-value field with two alternatives."""
    return ExtractedField(
        status="conflicting",
        alternatives=[
            Alternative(value="synthetic A", evidence=[EVIDENCE]),
            Alternative(value="synthetic B", evidence=[OTHER_EVIDENCE]),
        ],
        warning="Sources disagree",
    )


def rules_found(output: ExtractionOutput, field_rules: FieldRules) -> list[str]:
    """Return the rule names of every violation in a response."""
    violations: list[StatusViolation] = find_status_violations(output, field_rules, CHUNK_IDS)
    return [violation.rule for violation in violations]


@pytest.fixture
def rules(bundle: ConfigBundle) -> FieldRules:
    """Return the client field rules."""
    return bundle.field_rules


@pytest.fixture
def output(rules: FieldRules) -> ExtractionOutput:
    """Return a fresh valid response that a test can break."""
    return build_valid_output(rules)


def set_single_field(output: ExtractionOutput, rules: FieldRules, field: ExtractedField) -> None:
    """Replace the single-value test field of the first record."""
    output.records[0].fields[single_key(rules)] = field


def test_valid_output_has_no_violations(output: ExtractionOutput, rules: FieldRules) -> None:
    """A response that follows every rule gives no violations."""
    assert rules_found(output, rules) == []


def test_valid_conflicting_field_has_no_violations(
    output: ExtractionOutput, rules: FieldRules
) -> None:
    """A conflicting field with two cited alternatives and a warning is fine."""
    set_single_field(output, rules, build_conflicting_field())
    assert rules_found(output, rules) == []


def test_duplicate_record_ref_is_violation(output: ExtractionOutput, rules: FieldRules) -> None:
    """Two records with the same record_ref are reported."""
    output.records.append(output.records[0].model_copy())
    assert "duplicate_record_ref" in rules_found(output, rules)


def test_empty_found_in_is_violation(output: ExtractionOutput, rules: FieldRules) -> None:
    """A record must name at least one chunk in found_in."""
    output.records[0].found_in = []
    assert rules_found(output, rules) == ["found_in_empty"]


def test_unknown_found_in_chunk_is_violation(output: ExtractionOutput, rules: FieldRules) -> None:
    """A found_in chunk ID that is not in the run is reported."""
    output.records[0].found_in.append("doc09-p01-c999")
    assert rules_found(output, rules) == ["unknown_chunk_id"]


def test_unknown_evidence_chunk_is_violation(output: ExtractionOutput, rules: FieldRules) -> None:
    """An evidence pair citing a chunk that does not exist is reported, with the field."""
    bad_evidence = Evidence(chunk_id="doc09-p01-c999", quote="synthetic quote")
    set_single_field(
        output, rules, ExtractedField(status="found", value="v", evidence=[bad_evidence])
    )
    violations = find_status_violations(output, rules, CHUNK_IDS)
    assert [violation.rule for violation in violations] == ["unknown_chunk_id"]
    assert violations[0].field == single_key(rules)


def test_unknown_alternative_chunk_is_violation(
    output: ExtractionOutput, rules: FieldRules
) -> None:
    """Evidence inside an alternative must also cite a real chunk."""
    field = build_conflicting_field()
    field.alternatives[0].evidence = [Evidence(chunk_id="doc09-p01-c999", quote="q")]
    set_single_field(output, rules, field)
    assert rules_found(output, rules) == ["unknown_chunk_id"]


def test_unknown_excluded_item_chunk_is_violation(
    output: ExtractionOutput, rules: FieldRules
) -> None:
    """An excluded item citing a chunk that does not exist is reported."""
    output.excluded_items[0].chunk_ids = ["doc09-p01-c999"]
    assert rules_found(output, rules) == ["unknown_chunk_id"]


def test_missing_extracted_field_is_violation(output: ExtractionOutput, rules: FieldRules) -> None:
    """Every extracted field must be returned, even when not found."""
    del output.records[0].fields[single_key(rules)]
    assert rules_found(output, rules) == ["field_missing"]


def test_non_extracted_field_is_violation(output: ExtractionOutput, rules: FieldRules) -> None:
    """A field with another role (blank_for_now, system) must not be returned."""
    other_key = next(field.key for field in rules.fields if field.role != "extracted")
    output.records[0].fields[other_key] = ExtractedField(status="not_found")
    assert rules_found(output, rules) == ["field_not_extracted"]


def test_list_value_for_single_field_is_violation(
    output: ExtractionOutput, rules: FieldRules
) -> None:
    """A single-value field must not hold a list."""
    set_single_field(
        output, rules, ExtractedField(status="found", value=["a"], evidence=[EVIDENCE])
    )
    assert rules_found(output, rules) == ["value_wrong_shape"]


def test_text_value_for_multi_value_field_is_violation(
    output: ExtractionOutput, rules: FieldRules
) -> None:
    """A multi_value field must hold a list, not a single string."""
    field = ExtractedField(status="found", value="SYN-1", evidence=[EVIDENCE])
    output.records[0].fields[multi_key(rules)] = field
    assert rules_found(output, rules) == ["value_wrong_shape"]


def test_found_without_value_is_violation(output: ExtractionOutput, rules: FieldRules) -> None:
    """A found field needs a value."""
    set_single_field(output, rules, ExtractedField(status="found", evidence=[EVIDENCE]))
    assert rules_found(output, rules) == ["found_without_value"]


def test_found_with_blank_value_is_violation(output: ExtractionOutput, rules: FieldRules) -> None:
    """A found field whose value is only whitespace has no value."""
    set_single_field(output, rules, ExtractedField(status="found", value="  ", evidence=[EVIDENCE]))
    assert rules_found(output, rules) == ["found_without_value"]


def test_found_with_empty_list_is_violation(output: ExtractionOutput, rules: FieldRules) -> None:
    """A found multi_value field needs at least one value."""
    field = ExtractedField(status="found", value=[], evidence=[EVIDENCE])
    output.records[0].fields[multi_key(rules)] = field
    assert rules_found(output, rules) == ["found_without_value"]


def test_found_without_evidence_is_violation(output: ExtractionOutput, rules: FieldRules) -> None:
    """A found field needs at least one evidence pair."""
    set_single_field(output, rules, ExtractedField(status="found", value="v"))
    assert rules_found(output, rules) == ["found_without_evidence"]


def test_found_with_alternatives_is_violation(output: ExtractionOutput, rules: FieldRules) -> None:
    """A found field must not list alternatives."""
    alternatives = build_conflicting_field().alternatives
    field = ExtractedField(
        status="found", value="v", evidence=[EVIDENCE], alternatives=alternatives
    )
    set_single_field(output, rules, field)
    assert rules_found(output, rules) == ["found_with_alternatives"]


def test_conflicting_with_value_is_violation(output: ExtractionOutput, rules: FieldRules) -> None:
    """A conflicting field must not choose a value."""
    field = build_conflicting_field()
    field.value = "synthetic A"
    set_single_field(output, rules, field)
    assert rules_found(output, rules) == ["conflicting_with_value"]


def test_conflicting_with_evidence_is_violation(
    output: ExtractionOutput, rules: FieldRules
) -> None:
    """A conflicting field keeps its evidence in the alternatives only."""
    field = build_conflicting_field()
    field.evidence = [EVIDENCE]
    set_single_field(output, rules, field)
    assert rules_found(output, rules) == ["conflicting_with_evidence"]


def test_conflicting_without_two_alternatives_is_violation(
    output: ExtractionOutput, rules: FieldRules
) -> None:
    """A conflicting field needs at least two alternatives."""
    field = build_conflicting_field()
    field.alternatives = field.alternatives[:1]
    set_single_field(output, rules, field)
    assert rules_found(output, rules) == ["conflicting_without_two_alternatives"]


def test_alternative_without_value_is_violation(
    output: ExtractionOutput, rules: FieldRules
) -> None:
    """Each alternative needs a value."""
    field = build_conflicting_field()
    field.alternatives[1].value = ""
    set_single_field(output, rules, field)
    assert rules_found(output, rules) == ["alternative_without_value"]


def test_alternative_without_evidence_is_violation(
    output: ExtractionOutput, rules: FieldRules
) -> None:
    """Each alternative needs at least one evidence pair."""
    field = build_conflicting_field()
    field.alternatives[1].evidence = []
    set_single_field(output, rules, field)
    assert rules_found(output, rules) == ["alternative_without_evidence"]


def test_conflicting_without_warning_is_violation(
    output: ExtractionOutput, rules: FieldRules
) -> None:
    """A conflicting field needs a warning that says what the conflict is."""
    field = build_conflicting_field()
    field.warning = None
    set_single_field(output, rules, field)
    assert rules_found(output, rules) == ["conflicting_without_warning"]


def test_not_found_with_value_is_violation(output: ExtractionOutput, rules: FieldRules) -> None:
    """A not_found field must have a null value (never a filled-in one)."""
    set_single_field(output, rules, ExtractedField(status="not_found", value="v"))
    assert rules_found(output, rules) == ["not_found_with_value"]


def test_not_found_with_evidence_is_violation(output: ExtractionOutput, rules: FieldRules) -> None:
    """A not_found field must have no evidence."""
    set_single_field(output, rules, ExtractedField(status="not_found", evidence=[EVIDENCE]))
    assert rules_found(output, rules) == ["not_found_with_evidence"]


def test_not_found_with_alternatives_is_violation(
    output: ExtractionOutput, rules: FieldRules
) -> None:
    """A not_found field must have no alternatives."""
    alternatives = build_conflicting_field().alternatives
    set_single_field(output, rules, ExtractedField(status="not_found", alternatives=alternatives))
    assert rules_found(output, rules) == ["not_found_with_alternatives"]


def test_violation_messages_hold_no_values(output: ExtractionOutput, rules: FieldRules) -> None:
    """Messages name records and fields only, so they are safe to log."""
    set_single_field(output, rules, ExtractedField(status="not_found", value="secret synthetic"))
    violations = find_status_violations(output, rules, CHUNK_IDS)
    assert violations
    assert all("secret synthetic" not in violation.message for violation in violations)
