"""M5 validation tests: notes, unclear values, context findings, names, derived, catalog numbers.

Field keys, lookup values and table cells are read from the client config, never written here.
"""

from pathlib import Path

from app.assembly.assemble import assemble_record
from app.config.bundle import ConfigBundle
from app.contracts.extraction import ExtractedField
from app.contracts.issue import Issue
from app.contracts.record import (
    FieldNormalization,
    StoredContextAttribute,
    StoredRecord,
    Suggestion,
)
from app.contracts.reference import ReferenceData
from app.normalization.normalize import normalize_record
from app.normalization.notes import TransformNote
from app.validation import codes
from app.validation.duplicates import NAME_AS_WRITTEN
from app.validation.judge_cache import InMemoryJudgeCache, JudgeRunner
from app.validation.service import make_validation_config, validate_run
from tests.conftest import assert_config_error
from tests.unit import record_helpers
from tests.unit.validation_helpers import (
    JUDGE_PROMPT_VERSION,
    FakeJudge,
    find_rule,
    issues_with_code,
    make_record,
    make_reference,
    run_validation,
    set_output,
    update_field,
)

SYNTHETIC_NAME = "Syn Suggested Name"


def only_issue(issues: list[Issue]) -> Issue:
    """Return the one issue in a list."""
    assert len(issues) == 1, issues
    return issues[0]


def with_suggestion(record: StoredRecord, key: str, value: str, source: str) -> StoredRecord:
    """Return the record with a suggestion on one field."""
    suggestion = Suggestion.model_validate(
        {"value": value, "source": source, "reason": "synthetic reason", "rule_id": None}
    )
    stored = record.fields[key].model_copy(update={"suggestion": suggestion})
    return update_field(record, key, stored)


def with_catalog_number(reference: ReferenceData, catalog_no: str) -> ReferenceData:
    """Return the reference data with this catalog number on its first type."""
    first = reference.types[0].model_copy(update={"catalog_no": catalog_no})
    return reference.model_copy(update={"types": [first, *reference.types[1:]]})


def name_key(bundle: ConfigBundle) -> str:
    """Return the record name field's key."""
    return bundle.business_rules.record_name_field().key


def lookup_key(bundle: ConfigBundle) -> str:
    """Return the key of a plain lookup field (not derived, not the name)."""
    return find_rule(bundle.business_rules, lambda rule: rule.lookup_sheet is not None).key


# ----- Notes become issues -----


def test_reviewer_choice_note_raises_a_warning_with_the_choices(bundle: ConfigBundle) -> None:
    """REVIEWER_CHOICE_NEEDED is yellow, individual review, and carries the choices."""
    key = lookup_key(bundle)
    note = TransformNote(code="REVIEWER_CHOICE_NEEDED", original="synthetic phrase").to_text()
    record = set_output(make_record(bundle), key, None, changes=[note])
    stored = record.fields[key].model_copy(
        update={"normalization": FieldNormalization(choices=["Synthetic A", "Synthetic B"])}
    )
    result = run_validation(bundle, [update_field(record, key, stored)])
    issue = only_issue(issues_with_code(result, codes.REVIEWER_CHOICE_NEEDED))
    assert (issue.severity, issue.individual_review) == ("warning", True)
    assert issue.details == {"choices": ["Synthetic A", "Synthetic B"]}
    assert "Synthetic A, Synthetic B" in issue.message
    # The blank is explained by the note, so it is not also "not found"
    assert issues_with_code(result, codes.OPTIONAL_NOT_FOUND) == [] or all(
        i.field != key for i in issues_with_code(result, codes.OPTIONAL_NOT_FOUND)
    )


def test_not_a_concentration_note_raises_a_warning(bundle: ConfigBundle) -> None:
    """NOT_A_CONCENTRATION is yellow, and the blank it explains gives no OPTIONAL_NOT_FOUND."""
    rule, _ = record_helpers.find_field_table(bundle, "Concentration units")
    note = TransformNote(code="NOT_A_CONCENTRATION", original="1:100").to_text()
    record = set_output(make_record(bundle), rule.key, None, changes=[note])
    result = run_validation(bundle, [record])
    issue = only_issue(issues_with_code(result, codes.NOT_A_CONCENTRATION))
    assert (issue.severity, issue.field) == ("warning", rule.key)
    assert not [
        i for i in issues_with_code(result, codes.OPTIONAL_NOT_FOUND) if i.field == rule.key
    ]


def test_conflict_closed_note_raises_an_info(bundle: ConfigBundle) -> None:
    """CONFLICT_CLOSED is grey information."""
    key = lookup_key(bundle)
    note = TransformNote(code="CONFLICT_CLOSED", original="a | b", value="a").to_text()
    result = run_validation(bundle, [set_output(make_record(bundle), key, "a", changes=[note])])
    assert only_issue(issues_with_code(result, codes.CONFLICT_CLOSED)).severity == "info"


def test_not_in_lookup_carries_the_matching_suggestion(bundle: ConfigBundle) -> None:
    """NOT_IN_LOOKUP lists the field's suggestion in its details when there is one."""
    key = lookup_key(bundle)
    record = set_output(make_record(bundle), key, "Synthetic unlisted value")
    record = with_suggestion(record, key, "Synthetic listed value", "matching")
    issue = only_issue(issues_with_code(run_validation(bundle, [record]), codes.NOT_IN_LOOKUP))
    assert issue.details["suggestion"]["value"] == "Synthetic listed value"  # type: ignore[index]


def test_derived_value_missing_is_an_error_and_the_blank_follow_ons_are_silent(
    bundle: ConfigBundle,
) -> None:
    """No vendor or heading: Class and Critical are errors; the fields that read them are not."""
    rules = bundle.business_rules
    blank = record_helpers.make_record(rules)
    assembled = assemble_record(normalize_record(blank, rules, bundle.lookup_lists), rules)
    result = run_validation(bundle, [assembled])
    missing = issues_with_code(result, codes.DERIVED_VALUE_MISSING)
    assert all(issue.severity == "error" for issue in missing)
    # Only the fields whose own derivation could not run raise it (Class and Critical)
    assert len(missing) == 2
    derived_keys = {rule.key for rule in rules.derived_fields()}
    assert {issue.field for issue in missing} < derived_keys


# ----- Unclear values and context findings -----


def test_unclear_value_raises_a_warning_showing_the_extraction_warning(
    bundle: ConfigBundle,
) -> None:
    """Status `unclear` gives VALUE_UNCLEAR: yellow, individual review, showing the warning."""
    key = lookup_key(bundle)
    record = make_record(bundle)
    unclear = ExtractedField(status="unclear", value="x", warning="Two readings are possible.")
    record = update_field(
        record, key, record.fields[key].model_copy(update={"extraction": unclear})
    )
    issue = only_issue(issues_with_code(run_validation(bundle, [record]), codes.VALUE_UNCLEAR))
    assert (issue.severity, issue.individual_review, issue.field) == ("warning", True, key)
    assert "Two readings are possible." in issue.message


def context_record(bundle: ConfigBundle, extraction: ExtractedField, citation: str) -> StoredRecord:
    """Return a record whose first context attribute has this extraction and citation result."""
    attribute = bundle.business_rules.context_fields()[0]
    verification = {"citation_check": citation, "verdict": None, "note": None}
    context = StoredContextAttribute.model_validate(
        {"extraction": extraction.model_dump(), "verification": verification}
    )
    return make_record(bundle).model_copy(update={"context": {attribute.key: context}})


def test_context_finding_is_raised_on_the_field_it_drives(bundle: ConfigBundle) -> None:
    """A citation problem on a context attribute becomes an issue on its `Drives` field."""
    attribute = bundle.business_rules.context_fields()[0]
    found = ExtractedField(status="found", value="synthetic heading")
    record = context_record(bundle, found, "not_verified")
    issue = only_issue(
        issues_with_code(run_validation(bundle, [record]), codes.CITATION_NOT_VERIFIED)
    )
    assert issue.field == attribute.drives


def test_unclear_context_attribute_is_raised_on_the_driven_field(bundle: ConfigBundle) -> None:
    """An unclear context attribute gives VALUE_UNCLEAR on its `Drives` field."""
    attribute = bundle.business_rules.context_fields()[0]
    unclear = ExtractedField(status="unclear", value="x", warning="Unclear heading.")
    record = context_record(bundle, unclear, "verified")
    issue = only_issue(issues_with_code(run_validation(bundle, [record]), codes.VALUE_UNCLEAR))
    assert issue.field == attribute.drives


def test_person_value_on_the_driven_field_ends_a_context_finding(bundle: ConfigBundle) -> None:
    """Once a person sets the driven field, the context attribute's finding no longer applies."""
    attribute = bundle.business_rules.context_fields()[0]
    found = ExtractedField(status="found", value="synthetic heading")
    record = context_record(bundle, found, "not_verified")
    value = record.fields[attribute.drives].output.value
    record = set_output(record, attribute.drives, value, origin="user_edited")
    assert issues_with_code(run_validation(bundle, [record]), codes.CITATION_NOT_VERIFIED) == []


# ----- Names -----


def test_empty_name_is_name_not_set_with_the_suggestion(bundle: ConfigBundle) -> None:
    """An empty name is a red NAME_NOT_SET (not REQUIRED_MISSING) carrying the suggestion."""
    key = name_key(bundle)
    record = with_suggestion(
        set_output(make_record(bundle), key, None), key, SYNTHETIC_NAME, "naming"
    )
    result = run_validation(bundle, [record])
    issue = only_issue(issues_with_code(result, codes.NAME_NOT_SET))
    assert (issue.severity, issue.field) == ("error", key)
    assert issue.details["suggestion"]["value"] == SYNTHETIC_NAME  # type: ignore[index]
    assert not [i for i in issues_with_code(result, codes.REQUIRED_MISSING) if i.field == key]


def test_empty_name_without_a_suggestion_is_still_name_not_set(bundle: ConfigBundle) -> None:
    """With no Naming suggestion, NAME_NOT_SET has no suggestion in its details."""
    record = set_output(make_record(bundle), name_key(bundle), None)
    issue = only_issue(issues_with_code(run_validation(bundle, [record]), codes.NAME_NOT_SET))
    assert "suggestion" not in issue.details


def test_in_run_duplicates_use_set_names_only(bundle: ConfigBundle) -> None:
    """Two records with the same suggested name and no set name are not run duplicates."""
    key = name_key(bundle)
    records = [
        with_suggestion(
            set_output(make_record(bundle, record_id), key, None), key, "Syn Same", "naming"
        )
        for record_id in ("rec_0001", "rec_0002")
    ]
    assert issues_with_code(run_validation(bundle, records), codes.DUPLICATE_IN_RUN) == []


def test_reference_check_uses_the_suggested_name_while_the_name_is_not_set(
    bundle: ConfigBundle,
) -> None:
    """A suggested name that already exists in LabVantage is flagged on the name field."""
    key = name_key(bundle)
    record = with_suggestion(
        set_output(make_record(bundle), key, None), key, SYNTHETIC_NAME, "naming"
    )
    result = run_validation(bundle, [record], reference=make_reference(SYNTHETIC_NAME))
    issue = only_issue(issues_with_code(result, codes.EXISTS_IN_LABVANTAGE))
    assert issue.field == key


def test_judge_sees_the_suggested_name_and_the_name_as_written(bundle: ConfigBundle) -> None:
    """While the name is not set the judge gets the suggestion, plus the name as written."""
    key = name_key(bundle)
    record = make_record(bundle)
    written = ExtractedField(status="found", value="Syn Name As Written")
    stored = record.fields[key].model_copy(update={"extraction": written})
    record = with_suggestion(update_field(record, key, stored), key, "Syn Similar Name", "naming")
    record = set_output(record, key, None)
    judge = FakeJudge()
    run_validation(bundle, [record], reference=make_reference("Syn Similar Names"), judge=judge)
    [request] = judge.requests
    assert request.values[key] == "Syn Similar Name"
    assert request.values[NAME_AS_WRITTEN] == "Syn Name As Written"


# ----- Catalog numbers -----


def test_existing_type_with_the_same_catalog_number_is_shortlisted(bundle: ConfigBundle) -> None:
    """A dissimilar name still reaches the judge when the catalog number is shared."""
    rules = bundle.business_rules
    catalog = find_rule(rules, lambda rule: rule.multi_value)
    record = set_output(make_record(bundle), catalog.key, "SYN-001, SYN-002")
    reference = with_catalog_number(make_reference("Zzzz Qqqq"), " syn-002 ")
    config = make_validation_config(bundle)
    config = config.model_copy(
        update={
            "reference_rules": config.reference_rules.model_copy(
                update={"catalog_number_field": catalog.key}
            )
        }
    )
    judge = FakeJudge()
    runner = JudgeRunner(judge, InMemoryJudgeCache(), JUDGE_PROMPT_VERSION, None)
    validate_run([record], config, runner, reference)
    [request] = judge.requests
    assert [candidate.name for candidate in request.candidates] == ["Zzzz Qqqq"]


def test_without_the_catalog_setting_a_shared_number_adds_no_candidate(
    bundle: ConfigBundle,
) -> None:
    """The catalog shortlist is off until the mapping names the field."""
    catalog = find_rule(bundle.business_rules, lambda rule: rule.multi_value)
    record = set_output(make_record(bundle), catalog.key, "SYN-001")
    reference = with_catalog_number(make_reference("Zzzz Qqqq"), "SYN-001")
    judge = FakeJudge()
    run_validation(bundle, [record], reference=reference, judge=judge)
    assert judge.requests == []


# ----- Derived-value check (8.5) -----


def derived_key_and_value(bundle: ConfigBundle) -> tuple[str, str]:
    """Return a derived field's key and a value from its lookup list."""
    rule = next(r for r in bundle.business_rules.derived_fields() if r.lookup_sheet is not None)
    assert rule.lookup_sheet is not None
    return rule.key, bundle.lookup_lists.sheets[rule.lookup_sheet][0]


def test_person_set_derived_value_that_differs_is_a_mismatch(bundle: ConfigBundle) -> None:
    """A derived field set by hand that differs from its derivation is yellow and needs a note."""
    key, value = derived_key_and_value(bundle)
    record = set_output(make_record(bundle), key, value, origin="user_edited")
    result = run_validation(bundle, [record])
    mismatches = [
        i for i in issues_with_code(result, codes.DERIVED_VALUE_MISMATCH) if i.field == key
    ]
    issue = only_issue(mismatches)
    assert (issue.severity, issue.individual_review, issue.note_required) == ("warning", True, True)


def test_person_set_derived_value_that_agrees_is_not_a_mismatch(bundle: ConfigBundle) -> None:
    """A person-set derived field equal to its derivation raises nothing."""
    rules = bundle.business_rules
    assembled = assemble_record(
        normalize_record(record_helpers.make_record(rules), rules, bundle.lookup_lists), rules
    )
    for rule in rules.derived_fields():
        output = assembled.fields[rule.key].output
        assembled = set_output(assembled, rule.key, output.value, origin="user_edited")
    result = run_validation(bundle, [assembled])
    assert issues_with_code(result, codes.DERIVED_VALUE_MISMATCH) == []


def test_assembled_derived_value_is_never_checked(bundle: ConfigBundle) -> None:
    """Only person-set values are compared; a derived value is the derivation by definition."""
    key, value = derived_key_and_value(bundle)
    record = set_output(make_record(bundle), key, value, origin="derived")
    assert issues_with_code(run_validation(bundle, [record]), codes.DERIVED_VALUE_MISMATCH) == []


# ----- Catalogue -----


def test_catalogue_has_the_new_codes_and_not_or_equivalent(bundle: ConfigBundle) -> None:
    """Every code of the redesign is in the catalogue at its level; OR_EQUIVALENT is gone."""
    catalogue = bundle.issue_catalogue
    assert "OR_EQUIVALENT" not in catalogue.all_codes()
    for code in (
        codes.VALUE_UNCLEAR,
        codes.NAME_NOT_SET,
        codes.REVIEWER_CHOICE_NEEDED,
        codes.NOT_A_CONCENTRATION,
        codes.DERIVED_VALUE_MISSING,
        codes.DERIVED_VALUE_MISMATCH,
        codes.CONFLICT_CLOSED,
        "PLAUSIBILITY_CHECK",
    ):
        assert code in catalogue.record_issues
    for code in ("MATCHING_SKIPPED", "NAMING_SKIPPED", "PLAUSIBILITY_SKIPPED"):
        assert code in catalogue.run_issues
    assert catalogue.record_issues[codes.CONFLICT_UNRESOLVED].severity == "error"


def test_catalog_number_field_that_is_not_a_field_is_reported(config_copy: Path) -> None:
    """A mapping that names an unknown field for catalog numbers stops loading."""
    path = config_copy / "reference_data_mapping.yaml"
    text = path.read_text(encoding="utf-8")
    path.write_text(text + "\n  catalog_number_field: synthetic_missing_field\n", encoding="utf-8")
    assert_config_error(config_copy, "'catalog_number_field' is 'synthetic_missing_field'")
