"""Validation tests: one per issue code validation raises, plus catalogue coverage.

Field keys and lookup values are read from the client config, never written here.
"""

import pytest

from app.config.bundle import ConfigBundle
from app.config.errors import ConfigError
from app.config.field_rules import BothOrNeitherGroup, OneOfGroup
from app.contracts.extraction import Alternative, Evidence, ExtractedField
from app.contracts.judge import JudgeVerdict
from app.contracts.record import FieldVerification, RecordVerification
from app.contracts.verification import (
    CitationCheck,
    ExcludedItemChallenge,
    FieldVerdict,
    MissedCandidate,
    RecordFinding,
    RecordVerdict,
    UnreportedConflict,
    VerificationOutput,
)
from app.transform.notes import TransformNote
from app.transform.transform import transform_record
from app.validation import codes
from app.validation.duplicates import find_name_rule
from app.validation.findings_to_issues import (
    CITATION_CODES,
    FIELD_VERDICT_CODES,
    RECORD_VERDICT_CODES,
)
from app.validation.service import ProcessingFindings, find_owned_codes
from tests.unit.validation_helpers import (
    FakeJudge,
    find_rule,
    issues_with_code,
    make_record,
    make_reference,
    run_validation,
    set_output,
    update_field,
)

# Codes raised outside validation: ingest (M3), the graph (M8) and app start (interrupted runs)
CODES_RAISED_ELSEWHERE = {
    "FILE_UNREADABLE",
    "SCANNED_PAGES",
    "LOADER_FILE_UPLOADED",
    "NO_RECORDS_FOUND",
    "DOCUMENT_SET_TOO_LARGE",
    "NO_READABLE_DOCUMENTS",
    "EXTRACTION_FAILED",
    "PROCESSING_INTERRUPTED",
}

EVIDENCE = Evidence(chunk_id="doc01-c001", quote="synthetic quote")


def test_every_catalogue_code_is_raised_somewhere(bundle: ConfigBundle) -> None:
    """Each catalogue code is raised by validation or listed as raised by ingest or the graph."""
    owned = find_owned_codes(bundle.field_rules)
    assert bundle.issue_catalogue.all_codes() == owned | CODES_RAISED_ELSEWHERE


def test_missing_required_field_is_red(bundle: ConfigBundle) -> None:
    """An empty required field gives REQUIRED_MISSING, an error."""
    rule = find_rule(bundle.field_rules, lambda rule: rule.requirement == "required")
    result = run_validation(bundle, [set_output(make_record(bundle), rule.key, None)])
    [issue] = issues_with_code(result, codes.REQUIRED_MISSING)
    assert (issue.field, issue.severity) == (rule.key, "error")
    assert rule.column in issue.message


def test_unmet_one_of_group_gives_its_code(bundle: ConfigBundle) -> None:
    """A one_of group with no complete option gives the group's issue code on the record."""
    group = next(
        g for g in bundle.field_rules.condition_groups.values() if isinstance(g, OneOfGroup)
    )
    record = make_record(bundle)
    for key in {key for option in group.options for key in option}:
        record = set_output(record, key, None)
    [issue] = issues_with_code(run_validation(bundle, [record]), group.issue_code)
    assert (issue.record_id, issue.field) == ("rec_0001", None)


def test_half_filled_pair_gives_its_code(bundle: ConfigBundle) -> None:
    """A both_or_neither group with only some fields filled gives the group's issue code."""
    group = next(
        g for g in bundle.field_rules.condition_groups.values() if isinstance(g, BothOrNeitherGroup)
    )
    record = set_output(make_record(bundle), group.fields[0], None)
    assert len(issues_with_code(run_validation(bundle, [record]), group.issue_code)) == 1


def test_or_equivalent_is_raised_once_per_record(bundle: ConfigBundle) -> None:
    """Two fields allowing an equivalent product give one OR_EQUIVALENT on the record."""
    record = make_record(bundle)
    for rule in bundle.field_rules.extracted_fields()[:2]:
        stored = record.fields[rule.key]
        assert stored.extraction is not None
        extraction = stored.extraction.model_copy(update={"allows_equivalent": True})
        record = update_field(
            record, rule.key, stored.model_copy(update={"extraction": extraction})
        )
    [issue] = issues_with_code(run_validation(bundle, [record]), codes.OR_EQUIVALENT)
    assert issue.field is None


def test_value_not_on_lookup_list_is_red(bundle: ConfigBundle) -> None:
    """A list field value that is not on its lookup list gives NOT_IN_LOOKUP."""
    rule = find_rule(bundle.field_rules, lambda rule: rule.lookup_sheet is not None)
    record = set_output(make_record(bundle), rule.key, "synthetic off-list")
    [issue] = issues_with_code(run_validation(bundle, [record]), codes.NOT_IN_LOOKUP)
    assert "'synthetic off-list'" in issue.message


def test_boolean_word_is_not_in_lookup(bundle: ConfigBundle) -> None:
    """A boolean field holding a word such as "Yes" gives NOT_IN_LOOKUP."""
    rule = find_rule(bundle.field_rules, lambda rule: rule.type == "boolean")
    record = set_output(make_record(bundle), rule.key, "Yes")
    [issue] = issues_with_code(run_validation(bundle, [record]), codes.NOT_IN_LOOKUP)
    assert issue.field == rule.key


def test_value_over_the_length_limit_is_too_long(bundle: ConfigBundle) -> None:
    """A text value longer than its limit gives TOO_LONG, naming the limit."""
    rule = find_rule(
        bundle.field_rules,
        lambda rule: rule.type == "text" and rule.lookup_sheet is None and bool(rule.max_length),
    )
    assert rule.max_length is not None
    record = set_output(make_record(bundle), rule.key, "x" * (rule.max_length + 1))
    [issue] = [
        i
        for i in issues_with_code(run_validation(bundle, [record]), codes.TOO_LONG)
        if i.field == rule.key
    ]
    assert str(rule.max_length) in issue.message


def test_default_longer_than_its_limit_is_too_long_on_every_record(bundle: ConfigBundle) -> None:
    """Expected and documented: a default over its own limit (workbook as written) is TOO_LONG."""
    rule = find_rule(
        bundle.field_rules,
        lambda rule: (
            rule.default is not None
            and rule.max_length is not None
            and len(rule.default) > rule.max_length
        ),
    )
    not_found = ExtractedField(status="not_found")
    record = update_field(
        make_record(bundle),
        rule.key,
        make_record(bundle).fields[rule.key].model_copy(update={"extraction": not_found}),
    )
    record = transform_record(record, bundle.field_rules, bundle.lookup_lists)
    result = run_validation(bundle, [record])
    field_codes = {issue.code for issue in result.issues if issue.field == rule.key}
    assert {codes.TOO_LONG, codes.DEFAULT_APPLIED} <= field_codes


@pytest.mark.parametrize(("field_type", "value"), [("decimal", "2-8"), ("integer", "1.5")])
def test_value_that_is_not_a_number_is_wrong_type(
    bundle: ConfigBundle, field_type: str, value: str
) -> None:
    """A number field holding something other than a plain number gives WRONG_TYPE."""
    rule = find_rule(bundle.field_rules, lambda rule: rule.type == field_type)
    record = set_output(make_record(bundle), rule.key, value)
    [issue] = issues_with_code(run_validation(bundle, [record]), codes.WRONG_TYPE)
    assert issue.field == rule.key


@pytest.mark.parametrize("value", ["Syn α antibody", "Syn\x07A"])
def test_greek_or_control_characters_are_invalid(bundle: ConfigBundle, value: str) -> None:
    """A Greek letter or control character in a field that disallows them is INVALID_CHARACTERS."""
    rule = find_rule(bundle.field_rules, lambda rule: len(rule.disallowed_characters) == 2)
    record = set_output(make_record(bundle), rule.key, value)
    [issue] = issues_with_code(run_validation(bundle, [record]), codes.INVALID_CHARACTERS)
    assert issue.field == rule.key


def test_same_name_twice_in_run_is_red_on_both(bundle: ConfigBundle) -> None:
    """Two records with the same name each get DUPLICATE_IN_RUN on the name field."""
    records = [make_record(bundle, "rec_0001", "Syn A"), make_record(bundle, "rec_0002", "Syn A")]
    issues = issues_with_code(run_validation(bundle, records), codes.DUPLICATE_IN_RUN)
    assert sorted(issue.record_id or "" for issue in issues) == ["rec_0001", "rec_0002"]
    assert {issue.field for issue in issues} == {find_name_rule(bundle.field_rules).key}


def test_exact_reference_match_is_red_even_when_inactive(bundle: ConfigBundle) -> None:
    """An existing type with exactly the same name gives EXISTS_IN_LABVANTAGE, active or not."""
    judge = FakeJudge("same")
    reference = make_reference("Syn A", active_flag="N")
    result = run_validation(bundle, [make_record(bundle)], reference=reference, judge=judge)
    [issue] = issues_with_code(result, codes.EXISTS_IN_LABVANTAGE)
    assert issue.severity == "error"
    assert judge.requests == []


def test_conflict_without_a_choice_is_red(bundle: ConfigBundle) -> None:
    """A conflicting field with no value picked gives CONFLICT_UNRESOLVED."""
    rule = find_rule(bundle.field_rules, lambda rule: rule.requirement == "optional")
    alternatives = [Alternative(value=v, evidence=[EVIDENCE]) for v in ("syn 1", "syn 2")]
    conflict = ExtractedField(status="conflicting", alternatives=alternatives, warning="differ")
    record = make_record(bundle)
    stored = record.fields[rule.key].model_copy(update={"extraction": conflict})
    record = set_output(update_field(record, rule.key, stored), rule.key, None)
    result = run_validation(bundle, [record])
    assert [i.field for i in issues_with_code(result, codes.CONFLICT_UNRESOLVED)] == [rule.key]
    assert issues_with_code(result, codes.OPTIONAL_NOT_FOUND) == []


@pytest.mark.parametrize("verdict", list(FIELD_VERDICT_CODES))
def test_field_verdict_becomes_its_issue(bundle: ConfigBundle, verdict: FieldVerdict) -> None:
    """Each verification field verdict gives its code (contradicted, unsupported, missed)."""
    rule = bundle.field_rules.extracted_fields()[0]
    verification = FieldVerification(citation_check="verified", verdict=verdict, note="syn note")
    record = make_record(bundle)
    stored = record.fields[rule.key].model_copy(update={"verification": verification})
    result = run_validation(bundle, [update_field(record, rule.key, stored)])
    [issue] = issues_with_code(result, FIELD_VERDICT_CODES[verdict])
    assert issue.details["note"] == "syn note"


@pytest.mark.parametrize("check", list(CITATION_CODES))
def test_citation_result_becomes_its_issue(bundle: ConfigBundle, check: CitationCheck) -> None:
    """A not_verified citation gives CITATION_NOT_VERIFIED; not_checkable gives SCANNED_SOURCE."""
    rule = bundle.field_rules.extracted_fields()[0]
    record = make_record(bundle)
    verification = FieldVerification(citation_check=check)
    stored = record.fields[rule.key].model_copy(update={"verification": verification})
    result = run_validation(bundle, [update_field(record, rule.key, stored)])
    assert len(issues_with_code(result, CITATION_CODES[check])) == 1


def test_finding_no_longer_applies_after_a_person_sets_the_value(bundle: ConfigBundle) -> None:
    """A verdict on the extracted value is not raised once the value is user-edited."""
    rule = bundle.field_rules.extracted_fields()[0]
    verification = FieldVerification(citation_check="not_verified", verdict="unsupported", note="n")
    record = make_record(bundle)
    stored = record.fields[rule.key].model_copy(update={"verification": verification})
    record = set_output(update_field(record, rule.key, stored), rule.key, "Syn B", "user_edited")
    result = run_validation(bundle, [record])
    assert issues_with_code(result, codes.UNSUPPORTED_BY_SOURCE) == []
    assert issues_with_code(result, codes.CITATION_NOT_VERIFIED) == []


def test_normalized_reference_match_is_possible_duplicate_without_judge(
    bundle: ConfigBundle,
) -> None:
    """The same name apart from case and spaces gives POSSIBLE_DUPLICATE with no judge call."""
    judge = FakeJudge("different")
    reference = make_reference("SYN  a")
    result = run_validation(bundle, [make_record(bundle)], reference=reference, judge=judge)
    [issue] = issues_with_code(result, codes.POSSIBLE_DUPLICATE)
    assert issue.severity == "warning"
    assert judge.requests == []


@pytest.mark.parametrize(
    ("verdict", "is_raised"), [("same", True), ("unsure", True), ("different", False)]
)
def test_judge_same_or_unsure_is_possible_duplicate(
    bundle: ConfigBundle, verdict: JudgeVerdict, is_raised: bool
) -> None:
    """A similar existing type judged same or unsure is POSSIBLE_DUPLICATE; different is not."""
    judge = FakeJudge(verdict)
    record = make_record(bundle, name="Syn Buffer 10uM")
    reference = make_reference("Syn Buffer 100uM")
    result = run_validation(bundle, [record], reference=reference, judge=judge)
    assert len(judge.requests) == 1
    assert len(issues_with_code(result, codes.POSSIBLE_DUPLICATE)) == (1 if is_raised else 0)


@pytest.mark.parametrize(
    "note",
    [
        TransformNote(code="DEFAULT_APPLIED", value="1"),
        TransformNote(code="FORMAT_CORRECTED", original="syn 1", value="1"),
        TransformNote(code="NUMBER_READ_FROM_TEXT", original="1 syn", value="1"),
    ],
)
def test_transform_note_becomes_its_issue(bundle: ConfigBundle, note: TransformNote) -> None:
    """A coded transform note in output.changes gives its issue, filled from the note."""
    rule = find_rule(bundle.field_rules, lambda rule: rule.type == "decimal")
    record = set_output(make_record(bundle), rule.key, "1", changes=[note.to_text()])
    [issue] = issues_with_code(run_validation(bundle, [record]), note.code)
    assert issue.field == rule.key
    assert "{" not in issue.message


@pytest.mark.parametrize("verdict", list(RECORD_VERDICT_CODES))
def test_record_verdict_becomes_its_issue(bundle: ConfigBundle, verdict: RecordVerdict) -> None:
    """Each verification record verdict gives its record-level code."""
    finding = RecordFinding(record_id="rec_0001", verdict=verdict, note="Same as rec_0002")
    record = make_record(bundle).model_copy(
        update={"verification": RecordVerification(findings=[finding])}
    )
    records = [record, make_record(bundle, "rec_0002", "Syn B")]
    [issue] = issues_with_code(run_validation(bundle, records), RECORD_VERDICT_CODES[verdict])
    assert (issue.record_id, issue.field) == ("rec_0001", None)
    assert "{" not in issue.message


def test_possible_duplicate_in_run_names_the_other_record(bundle: ConfigBundle) -> None:
    """POSSIBLE_DUPLICATE_IN_RUN fills {other} with the run records the agent's note names."""
    finding = RecordFinding(
        record_id="rec_0001", verdict="duplicate_within_run", note="Same as rec_0002"
    )
    record = make_record(bundle).model_copy(
        update={"verification": RecordVerification(findings=[finding])}
    )
    records = [record, make_record(bundle, "rec_0002", "Syn B")]
    [issue] = issues_with_code(run_validation(bundle, records), codes.POSSIBLE_DUPLICATE_IN_RUN)
    assert "rec_0002" in issue.message


def test_empty_optional_field_is_grey(bundle: ConfigBundle) -> None:
    """An optional field with no value gives OPTIONAL_NOT_FOUND, info."""
    rule = find_rule(bundle.field_rules, lambda rule: rule.requirement == "optional")
    record = set_output(make_record(bundle), rule.key, None)
    [issue] = issues_with_code(run_validation(bundle, [record]), codes.OPTIONAL_NOT_FOUND)
    assert (issue.field, issue.severity) == (rule.key, "info")


def test_unreported_conflict_is_an_individual_review_warning(bundle: ConfigBundle) -> None:
    """An unreported conflict from verification gives UNREPORTED_CONFLICT on that field."""
    rule = bundle.field_rules.extracted_fields()[1]
    conflict = UnreportedConflict(
        record_id="rec_0001", field=rule.key, sources=["doc01-c002"], note="syn note"
    )
    findings = ProcessingFindings(verification=make_verification(unreported_conflicts=[conflict]))
    result = run_validation(bundle, [make_record(bundle)], findings=findings)
    [issue] = issues_with_code(result, codes.UNREPORTED_CONFLICT)
    assert (issue.field, issue.individual_review) == (rule.key, True)


def test_dropped_record_is_flagged(bundle: ConfigBundle) -> None:
    """A record re-extraction did not return gives RECORD_DROPPED_ON_REEXTRACTION."""
    findings = ProcessingFindings(dropped_record_ids=["rec_0001"])
    result = run_validation(bundle, [make_record(bundle)], findings=findings)
    assert len(issues_with_code(result, codes.RECORD_DROPPED_ON_REEXTRACTION)) == 1


def test_missed_candidates_and_challenged_items_are_run_issues(bundle: ConfigBundle) -> None:
    """Missed candidates and challenged excluded items each give one run issue listing them."""
    verification = make_verification(
        missed_candidates=[MissedCandidate(name_as_written="Syn X", sources=[], reason="r")],
        excluded_item_challenges=[ExcludedItemChallenge(item="Syn Y", reason="r")],
    )
    result = run_validation(bundle, [], findings=ProcessingFindings(verification=verification))
    [missed] = issues_with_code(result, codes.MISSED_CANDIDATES_UNRESOLVED)
    [challenged] = issues_with_code(result, codes.EXCLUDED_ITEM_CHALLENGED)
    assert "Syn X" in missed.message and missed.record_id is None
    assert "Syn Y" in challenged.message and challenged.individual_review


def test_no_reference_data_is_a_run_warning(bundle: ConfigBundle) -> None:
    """Without reference data the check is skipped with one REFERENCE_DATA_MISSING run issue."""
    judge = FakeJudge("same")
    result = run_validation(bundle, [make_record(bundle)], reference=None, judge=judge)
    [issue] = issues_with_code(result, codes.REFERENCE_DATA_MISSING)
    assert (issue.record_id, issue.severity) == (None, "warning")
    assert judge.requests == []


def test_judge_limit_skips_the_rest_with_a_count(bundle: ConfigBundle) -> None:
    """Over the call limit, records are not judged and DUPLICATE_CHECK_SKIPPED counts them."""
    judge = FakeJudge("different")
    records = [make_record(bundle, f"rec_000{n}", f"Syn Buffer {n}0uM") for n in (1, 2, 3)]
    reference = make_reference("Syn Buffer 100uM")
    result = run_validation(bundle, records, reference=reference, judge=judge, call_limit=1)
    assert (len(judge.requests), result.judge_calls_made) == (1, 1)
    [issue] = issues_with_code(result, codes.DUPLICATE_CHECK_SKIPPED)
    assert issue.details["count"] == 2
    assert "2" in issue.message


def test_missing_catalogue_code_is_a_config_error(bundle: ConfigBundle) -> None:
    """A code validation raises but the catalogue lacks stops with a ConfigError naming it."""
    catalogue = bundle.issue_catalogue.model_copy(update={"run_issues": {}})
    broken = bundle.model_copy(update={"issue_catalogue": catalogue})
    with pytest.raises(ConfigError, match=codes.REFERENCE_DATA_MISSING):
        run_validation(broken, [], reference=None)


def make_verification(
    unreported_conflicts: list[UnreportedConflict] | None = None,
    missed_candidates: list[MissedCandidate] | None = None,
    excluded_item_challenges: list[ExcludedItemChallenge] | None = None,
) -> VerificationOutput:
    """Return a verification output with only the given lists filled."""
    return VerificationOutput(
        field_findings=[],
        record_findings=[],
        missed_candidates=missed_candidates or [],
        excluded_item_challenges=excluded_item_challenges or [],
        unreported_conflicts=unreported_conflicts or [],
    )
