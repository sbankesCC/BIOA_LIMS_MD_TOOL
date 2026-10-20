"""Validation service tests: judge cache and limit, values untouched, lifecycle, action needed.

Field keys and lookup values are read from the client config, never written here.
"""

from datetime import UTC, datetime

import pytest

from app.config.bundle import ConfigBundle
from app.contracts.issue import Issue, IssueSeverity, IssueStatus
from app.contracts.record import Exclusion
from app.validation import codes
from app.validation.action_needed import compute_action_needed
from app.validation.duplicates import build_shortlist
from app.validation.judge_cache import InMemoryJudgeCache, make_judge_cache_key
from tests.unit.validation_helpers import (
    FakeJudge,
    find_rule,
    issues_with_code,
    make_record,
    make_reference,
    run_validation,
    set_output,
)

SIMILAR_NAME = "Syn Buffer 10uM"
REFERENCE = make_reference("Syn Buffer 100uM")


def test_cache_hit_skips_the_judge_on_recheck(bundle: ConfigBundle) -> None:
    """A second pass with unchanged identifying values uses the cache, not the judge."""
    judge, cache = FakeJudge("same"), InMemoryJudgeCache()
    records = [make_record(bundle, name=SIMILAR_NAME)]
    first = run_validation(bundle, records, reference=REFERENCE, judge=judge, cache=cache)
    second = run_validation(bundle, records, reference=REFERENCE, judge=judge, cache=cache)
    assert (first.judge_calls_made, second.judge_calls_made, len(judge.requests)) == (1, 0, 1)
    assert len(issues_with_code(second, codes.POSSIBLE_DUPLICATE)) == 1


def test_changed_identifying_value_misses_the_cache(bundle: ConfigBundle) -> None:
    """Changing an extracted value the judge sees calls the judge again."""
    judge, cache = FakeJudge("different"), InMemoryJudgeCache()
    record = make_record(bundle, name=SIMILAR_NAME)
    run_validation(bundle, [record], reference=REFERENCE, judge=judge, cache=cache)
    rule = bundle.field_rules.extracted_fields()[1]
    changed = set_output(record, rule.key, "synthetic other", "user_edited")
    run_validation(bundle, [changed], reference=REFERENCE, judge=judge, cache=cache)
    assert len(judge.requests) == 2


def test_cache_key_changes_with_reference_and_prompt_version() -> None:
    """The cache key depends on the values, the reference data version and the prompt version."""
    values: dict[str, str | None] = {"a": "1", "b": None}
    key = make_judge_cache_key(values, "ref-1", "p-1")
    assert key == make_judge_cache_key({"b": None, "a": "1"}, "ref-1", "p-1")
    assert key != make_judge_cache_key(values, "ref-2", "p-1")
    assert key != make_judge_cache_key(values, "ref-1", "p-2")
    assert key != make_judge_cache_key({"a": "2", "b": None}, "ref-1", "p-1")


def test_blank_judge_limit_means_no_limit(bundle: ConfigBundle) -> None:
    """With no call limit every record with a shortlist is judged and nothing is skipped."""
    judge = FakeJudge("different")
    records = [make_record(bundle, f"rec_000{n}", f"Syn Buffer {n}0uM") for n in (1, 2, 3)]
    result = run_validation(bundle, records, reference=REFERENCE, judge=judge, call_limit=None)
    assert result.judge_calls_made == 3
    assert issues_with_code(result, codes.DUPLICATE_CHECK_SKIPPED) == []


def test_cached_results_do_not_count_against_the_limit(bundle: ConfigBundle) -> None:
    """With the limit used up, a cached result is still used and the record is not skipped."""
    judge, cache = FakeJudge("same"), InMemoryJudgeCache()
    records = [make_record(bundle, name=SIMILAR_NAME)]
    run_validation(bundle, records, reference=REFERENCE, judge=judge, cache=cache)
    result = run_validation(
        bundle, records, reference=REFERENCE, judge=judge, cache=cache, call_limit=0
    )
    assert issues_with_code(result, codes.DUPLICATE_CHECK_SKIPPED) == []
    assert len(issues_with_code(result, codes.POSSIBLE_DUPLICATE)) == 1


def test_shortlist_is_limited_and_most_similar_first(bundle: ConfigBundle) -> None:
    """The shortlist holds at most shortlist_size similar names, closest first, none unrelated."""
    size = bundle.reference_mapping.rules.shortlist_size
    names = [f"Syn Buffer {n}uM" for n in range(size + 5)] + ["Unrelated thing"]
    shortlist = build_shortlist("Syn Buffer 1uM", make_reference(*names).types, size)
    assert len(shortlist) == size
    assert shortlist[0].name == "Syn Buffer 1uM"
    assert "Unrelated thing" not in [existing.name for existing in shortlist]


def test_validation_never_changes_a_value(bundle: ConfigBundle) -> None:
    """Validation writes issue IDs and action needed only; every output section is unchanged."""
    rule = find_rule(bundle.field_rules, lambda rule: rule.lookup_sheet is not None)
    record = set_output(make_record(bundle, name=SIMILAR_NAME), rule.key, " syn off-list ")
    result = run_validation(bundle, [record], reference=REFERENCE, judge=FakeJudge("same"))
    [after] = result.records
    for key, stored in record.fields.items():
        assert after.fields[key].output == stored.output
        assert after.fields[key].extraction == stored.extraction
        assert after.fields[key].verification == stored.verification
    assert after.fields[rule.key].issue_ids != []


def test_blank_for_now_fields_are_not_validated(bundle: ConfigBundle) -> None:
    """A field with role blank_for_now gets no issue, whatever its value."""
    blank_rules = [rule for rule in bundle.field_rules.fields if rule.role == "blank_for_now"]
    record = make_record(bundle)
    for rule in blank_rules:
        record = set_output(record, rule.key, "x" * 500, origin="blank_for_now")
    result = run_validation(bundle, [record])
    blank_keys = {rule.key for rule in blank_rules}
    assert blank_keys
    assert [issue for issue in result.issues if issue.field in blank_keys] == []


def test_same_key_keeps_its_id_and_accepted_state(bundle: ConfigBundle) -> None:
    """A re-check that finds the same problem gives the same ID and keeps it accepted."""
    rule = find_rule(bundle.field_rules, lambda rule: rule.requirement == "optional")
    record = set_output(make_record(bundle), rule.key, None)
    first = run_validation(bundle, [record])
    [issue] = issues_with_code(first, codes.OPTIONAL_NOT_FOUND)
    accepted = accept(first.issues, issue.issue_id)
    second = run_validation(bundle, [record], previous_issues=accepted)
    [again] = [i for i in second.issues if i.issue_id == issue.issue_id]
    assert (again.status, again.closed_by) == ("accepted", "syn user")


def test_changed_value_resolves_the_old_issue(bundle: ConfigBundle) -> None:
    """When the value changes, the old issue is resolved and a new problem gets a new ID."""
    rule = find_rule(bundle.field_rules, lambda rule: rule.lookup_sheet is not None)
    first = run_validation(bundle, [set_output(make_record(bundle), rule.key, "syn off 1")])
    [old] = issues_with_code(first, codes.NOT_IN_LOOKUP)
    changed = set_output(make_record(bundle), rule.key, "syn off 2", "user_edited")
    second = run_validation(bundle, [changed], previous_issues=first.issues)
    [new] = issues_with_code(second, codes.NOT_IN_LOOKUP)
    [resolved] = [i for i in second.issues if i.issue_id == old.issue_id]
    assert resolved.status == "resolved"
    assert new.issue_id != old.issue_id
    assert second.records[0].fields[rule.key].issue_ids == [new.issue_id]


def test_issues_from_other_layers_are_kept(bundle: ConfigBundle) -> None:
    """An earlier issue with a code validation does not own (an ingest issue) stays open."""
    ingest_issue = Issue(
        issue_id="iss_ingest00001",
        code="FILE_UNREADABLE",
        severity="warning",
        record_id=None,
        field=None,
        message="synthetic",
    )
    result = run_validation(bundle, [make_record(bundle)], previous_issues=[ingest_issue])
    assert ingest_issue in result.issues


def test_excluded_record_is_skipped_and_keeps_its_issues(bundle: ConfigBundle) -> None:
    """An excluded record gets no new issues, keeps its earlier ones and needs no action."""
    rule = find_rule(bundle.field_rules, lambda rule: rule.requirement == "required")
    record = set_output(make_record(bundle), rule.key, None)
    first = run_validation(bundle, [record])
    exclusion = Exclusion(by="syn user", at=datetime.now(UTC), reason="synthetic")
    excluded = first.records[0].model_copy(update={"exclusion": exclusion})
    second = run_validation(bundle, [excluded], previous_issues=first.issues)
    assert second.issues == first.issues
    assert second.records[0].action_needed == "excluded"
    assert second.records[0].issue_ids == first.records[0].issue_ids


@pytest.mark.parametrize(
    ("severities", "expected"),
    [
        ([("error", "open"), ("warning", "open")], "fix"),
        ([("warning", "open"), ("info", "open")], "check"),
        ([("warning", "accepted"), ("info", "open"), ("error", "resolved")], "none"),
    ],
)
def test_action_needed_follows_open_issues(
    bundle: ConfigBundle, severities: list[tuple[IssueSeverity, IssueStatus]], expected: str
) -> None:
    """Open red gives fix; open yellow only gives check; accepted, resolved or grey give none."""
    record = make_record(bundle)
    issues = [
        Issue(
            issue_id=f"iss_{number}",
            code="SYN",
            severity=severity,
            record_id=record.record_id,
            field=None,
            message="synthetic",
            status=status,
        )
        for number, (severity, status) in enumerate(severities)
    ]
    assert compute_action_needed(record, issues) == expected


def test_record_with_open_red_issue_needs_fix(bundle: ConfigBundle) -> None:
    """The service sets action_needed on each record: a missing required value means fix."""
    rule = find_rule(bundle.field_rules, lambda rule: rule.requirement == "required")
    result = run_validation(bundle, [set_output(make_record(bundle), rule.key, None)])
    assert result.records[0].action_needed == "fix"


def accept(issues: list[Issue], issue_id: str) -> list[Issue]:
    """Return the issues with one of them accepted by a synthetic user."""
    return [
        issue.model_copy(update={"status": "accepted", "closed_by": "syn user"})
        if issue.issue_id == issue_id
        else issue
        for issue in issues
    ]
