"""Eval scoring tests: record matching, field values and status, citations and seeded errors.

Records and values are synthetic; field keys come from the client config, never written here.
"""

import pytest

from app.config.bundle import ConfigBundle
from app.config.field_rules import FieldRules
from app.contracts.eval_case import (
    ExpectedExtraction,
    ExpectedField,
    ExpectedRecord,
    ExpectedSource,
    SeededError,
)
from app.contracts.extraction import Alternative, Evidence, ExtractedField
from app.contracts.verification import FieldFinding
from app.evals.case_loader import load_scoring_config
from app.evals.scoring import (
    ActualRecord,
    ActualSource,
    Score,
    match_records,
    score_citations,
    score_field,
    score_run,
    select_scored_fields,
    values_equal,
)

CHUNK = Evidence(chunk_id="doc01-c001", quote="synthetic quote")
METHOD = "synthetic_method.docx"


def found(value: str | list[str]) -> ExtractedField:
    """Return a found extracted field with one evidence pair."""
    return ExtractedField(status="found", value=value, evidence=[CHUNK])


def not_found() -> ExtractedField:
    """Return a not_found extracted field."""
    return ExtractedField(status="not_found")


def conflicting(*values: str) -> ExtractedField:
    """Return a conflicting extracted field with one alternative per value."""
    alternatives = [Alternative(value=value, evidence=[CHUNK]) for value in values]
    return ExtractedField(status="conflicting", alternatives=alternatives, warning="synthetic")


def plain_key(field_rules: FieldRules, position: int = 0) -> str:
    """Return the key of an extracted, single-value field other than the record name."""
    name_key = field_rules.record_name_field().key
    keys = [
        rule.key
        for rule in field_rules.extracted_fields()
        if rule.key != name_key and not rule.multi_value
    ]
    return keys[position]


def scored_keys(field_rules: FieldRules) -> list[str]:
    """Return every extracted field key (nothing unscored)."""
    return [rule.key for rule in field_rules.extracted_fields()]


def actual_record(
    record_id: str, name: str, fields: dict[str, ExtractedField], field_rules: FieldRules
) -> ActualRecord:
    """Return a scoring record with the name field found and the given fields."""
    name_key = field_rules.record_name_field().key
    all_fields = {name_key: found(name), **fields}
    return ActualRecord(
        record_id=record_id,
        name=name,
        sources=[ActualSource(document=METHOD, section="Synthetic > 6.2 Reagents")],
        fields=dict(all_fields),
        output_values={key: None for key in all_fields},
    )


def expected_record(name: str, fields: dict[str, ExpectedField]) -> ExpectedRecord:
    """Return an expected record with the given labeled fields."""
    return ExpectedRecord(name=name, fields=fields)


def test_records_match_by_normalized_name() -> None:
    """Case, spaces and the degree sign are ignored; leftovers are listed on both sides."""
    expected = [expected_record("Synthetic Buffer A", {}), expected_record("Synthetic Gone", {})]
    actual = [
        ActualRecord(record_id="rec_0001", name="synthetic  buffer a"),
        ActualRecord(record_id="rec_0002", name="Synthetic Extra"),
    ]
    match = match_records(expected, actual)
    assert match.pairs == [(0, 0)]
    assert match.unmatched_expected == [1]
    assert match.unmatched_actual == [1]


def test_one_actual_record_matches_only_one_expected_record() -> None:
    """Two run records with the same name: the second one is unmatched (lowers precision)."""
    expected = [expected_record("Synthetic Buffer A", {})]
    actual = [
        ActualRecord(record_id="rec_0001", name="Synthetic Buffer A"),
        ActualRecord(record_id="rec_0002", name="Synthetic Buffer A"),
    ]
    match = match_records(expected, actual)
    assert match.pairs == [(0, 0)]
    assert match.unmatched_actual == [1]


def test_found_value_is_compared_with_whitespace_collapsed() -> None:
    """A found value equal apart from spacing is correct; another value is wrong."""
    label = ExpectedField(status="found", value="Synthetic Vendor One")
    assert score_field("key", label, found(" Synthetic  Vendor One"), None).is_value_correct
    wrong = score_field("key", label, found("Synthetic Vendor Two"), None)
    assert not wrong.is_value_correct
    assert wrong.is_status_correct


def test_found_value_may_match_the_exported_value() -> None:
    """A label written in the exported form counts as correct."""
    label = ExpectedField(status="found", value="synthetic exported form")
    as_written = found("synthetic as written")
    assert score_field("key", label, as_written, "synthetic exported form").is_value_correct


def test_list_values_compare_as_sets() -> None:
    """Catalog-number lists match in any order."""
    assert values_equal(["SYN-2", "SYN-1"], ["SYN-1", "SYN-2"])
    assert not values_equal(["SYN-1"], ["SYN-1", "SYN-2"])


def test_conflict_is_correct_only_with_the_same_alternatives() -> None:
    """A conflict needs the same alternatives (any order); a found value is a status error."""
    label = ExpectedField(status="conflicting", alternatives=["synthetic cold", "synthetic warm"])
    assert score_field(
        "key", label, conflicting("synthetic warm", "synthetic cold"), None
    ).is_value_correct
    assert not score_field(
        "key", label, conflicting("synthetic cold", "other"), None
    ).is_value_correct
    wrong_status = score_field("key", label, found("synthetic cold"), None)
    assert not wrong_status.is_status_correct
    assert not wrong_status.is_value_correct


def test_not_found_label_needs_not_found() -> None:
    """A not_found label is right only when nothing was extracted."""
    label = ExpectedField(status="not_found")
    assert score_field("key", label, not_found(), None).is_value_correct
    invented = score_field("key", label, found("synthetic invented value"), None)
    assert not invented.is_value_correct
    assert not invented.is_status_correct


def test_field_missing_from_the_run_is_wrong() -> None:
    """A labeled field the run did not return is wrong on value and status."""
    result = score_field("key", ExpectedField(status="not_found"), None, None)
    assert not result.is_value_correct
    assert not result.is_status_correct


def test_unlabeled_key_is_not_counted_as_wrong(bundle: ConfigBundle) -> None:
    """A field the case does not label is left out, whatever the run extracted for it."""
    rules = bundle.field_rules
    labeled, unlabeled = plain_key(rules, 0), plain_key(rules, 1)
    expected = ExpectedExtraction(
        records=[
            expected_record(
                "Synthetic Buffer A", {labeled: ExpectedField(status="found", value="x")}
            )
        ]
    )
    actual = actual_record(
        "rec_0001",
        "Synthetic Buffer A",
        {labeled: found("x"), unlabeled: found("synthetic value nobody labeled")},
        rules,
    )
    scoring = score_run(expected, [actual], scored_keys(rules), [], [], [])
    assert scoring.scores.field_values == Score(correct=1, total=1)
    assert unlabeled not in scoring.by_field


def test_unscored_field_is_left_out(bundle: ConfigBundle) -> None:
    """A labeled but unscored field is not counted, even when the run got it wrong."""
    rules = bundle.field_rules
    key = plain_key(rules)
    expected = ExpectedExtraction(
        records=[expected_record("Synthetic A", {key: ExpectedField(status="not_found")})]
    )
    actual = actual_record("rec_0001", "Synthetic A", {key: found("synthetic text")}, rules)
    scored = select_scored_fields(scored_keys(rules), {key})
    scoring = score_run(expected, [actual], scored, [], [], [])
    assert scoring.scores.field_values == Score(correct=0, total=0)


def test_description_is_excluded_from_scoring(bundle: ConfigBundle) -> None:
    """The evals scoring config leaves the description field out of automatic scoring."""
    keys = scored_keys(bundle.field_rules)
    unscored = load_scoring_config().unscored_keys()
    assert "description" in unscored
    assert "description" in keys
    assert "description" not in select_scored_fields(keys, unscored)


def test_citation_needs_the_expected_document_and_section() -> None:
    """A source counts when its document and section (or sheet, or page) match the label."""
    record = ActualRecord(
        record_id="rec_0001",
        name="Synthetic A",
        sources=[
            ActualSource(document=METHOD, section="Synthetic Method > 6 Materials > 6.2 Reagents"),
            ActualSource(document="synthetic_sheet.xlsx", sheet="Reagents"),
            ActualSource(document="synthetic_plan.pdf", page=4),
        ],
    )
    labels = [
        ExpectedSource(document=METHOD, section="6.2 Reagents"),
        ExpectedSource(document="synthetic_sheet.xlsx", section="Reagents"),
        ExpectedSource(document="synthetic_plan.pdf", page=4),
        ExpectedSource(document="synthetic_plan.pdf", page=5),
        ExpectedSource(document=METHOD, section="6.3 Equipment"),
    ]
    expected = ExpectedRecord(name="Synthetic A", found_in=labels)
    assert score_citations(expected, record) == Score(correct=3, total=5)
    assert score_citations(expected, None) == Score(correct=0, total=5)


def test_record_recall_and_precision(bundle: ConfigBundle) -> None:
    """Missed expected records lower recall; extra records lower precision."""
    rules = bundle.field_rules
    expected = ExpectedExtraction(
        records=[expected_record("Synthetic A", {}), expected_record("Synthetic B", {})]
    )
    actual = [
        actual_record("rec_0001", "Synthetic A", {}, rules),
        actual_record("rec_0002", "Synthetic Extra", {}, rules),
        actual_record("rec_0003", "Synthetic Extra 2", {}, rules),
    ]
    scoring = score_run(expected, actual, scored_keys(rules), [], [], [])
    assert scoring.scores.record_recall == Score(correct=1, total=2)
    assert scoring.scores.record_precision == Score(correct=1, total=3)
    assert scoring.unmatched_expected == ["Synthetic B"]
    assert scoring.unmatched_actual == ["rec_0002", "rec_0003"]


@pytest.mark.parametrize(("verdict", "is_caught"), [("contradicted", True), ("unsupported", False)])
def test_seeded_error_is_caught_with_the_expected_verdict(
    bundle: ConfigBundle, verdict: str, is_caught: bool
) -> None:
    """A planted error counts as caught only when a finding gives the expected verdict."""
    rules = bundle.field_rules
    key = plain_key(rules)
    error = SeededError(
        record="Synthetic A", field=key, planted_value="x", expected_verdict="contradicted"
    )
    finding = FieldFinding.model_validate(
        {"record_id": "rec_0001", "field": key, "verdict": verdict, "sources": [], "note": "s"}
    )
    actual = [actual_record("rec_0001", "Synthetic A", {}, rules)]
    expected = ExpectedExtraction(records=[expected_record("Synthetic A", {})])
    scoring = score_run(expected, actual, scored_keys(rules), [error], [error], [finding])
    assert scoring.scores.seeded_errors_caught == Score(correct=int(is_caught), total=1)
    assert scoring.seeded_errors[0].verdicts_given == [verdict]


def test_seeded_error_not_planted_is_not_counted(bundle: ConfigBundle) -> None:
    """An error that could not be planted is reported but not scored."""
    rules = bundle.field_rules
    error = SeededError(
        record="Synthetic A",
        field=plain_key(rules),
        planted_value="x",
        expected_verdict="unsupported",
    )
    expected = ExpectedExtraction(records=[expected_record("Synthetic A", {})])
    actual = [actual_record("rec_0001", "Synthetic A", {}, rules)]
    scoring = score_run(expected, actual, scored_keys(rules), [error], [], [])
    assert scoring.scores.seeded_errors_caught == Score(correct=0, total=0)
    assert not scoring.seeded_errors[0].is_planted


def test_finding_on_a_correct_value_counts_as_wrongly_flagged(bundle: ConfigBundle) -> None:
    """Verification flagging a value that matches the label is counted; seeded fields are not."""
    rules = bundle.field_rules
    good, seeded_key = plain_key(rules, 0), plain_key(rules, 1)
    labels = {
        good: ExpectedField(status="found", value="x"),
        seeded_key: ExpectedField(status="found", value="y"),
    }
    expected = ExpectedExtraction(records=[expected_record("Synthetic A", labels)])
    actual = [
        actual_record("rec_0001", "Synthetic A", {good: found("x"), seeded_key: found("y")}, rules)
    ]
    error = SeededError(
        record="Synthetic A", field=seeded_key, planted_value="z", expected_verdict="contradicted"
    )
    findings = [
        FieldFinding(record_id="rec_0001", field=key, verdict="contradicted", sources=[], note="s")
        for key in (good, seeded_key)
    ]
    scoring = score_run(expected, actual, scored_keys(rules), [error], [error], findings)
    # Only `good` is a correct, labeled, unseeded value, and it was flagged
    assert scoring.scores.correct_values_flagged == Score(correct=1, total=1)


def test_score_rate_is_empty_when_nothing_was_counted() -> None:
    """A score with no total has no rate, so a report does not show a fake 0 or 100%."""
    assert Score().rate is None
    assert Score(correct=1, total=4).rate == 0.25
