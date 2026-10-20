"""Duplicate candidate details: existing types carry description, class and active flag.

The attributes are copied from the reference data the validation pass is given (the run's pinned
version) and are None when it has none. Every name and value here is synthetic.
"""

from pydantic import JsonValue

from app.config.bundle import ConfigBundle
from app.contracts.issue import DuplicateCandidate, Issue
from app.contracts.reference import ReferenceData, ReferenceType
from app.ids import make_issue_id
from app.review.view import build_review_view, read_duplicate_candidates
from app.validation import codes
from app.validation.duplicates import find_name_rule
from tests.unit.validation_helpers import FakeJudge, issues_with_code, make_record, run_validation

# Synthetic attributes of an existing type
DESCRIPTION = "Synthetic existing description"
CLASS = "Synthetic class"
ACTIVE = "Y"


def make_described_reference(name: str, is_described: bool = True) -> ReferenceData:
    """Return synthetic reference data with one existing type, with or without its attributes."""
    existing = ReferenceType(
        candidate_id="ref_0001",
        name=name,
        version="1",
        description=DESCRIPTION if is_described else None,
        consumable_class=CLASS if is_described else None,
        active_flag=ACTIVE if is_described else None,
    )
    return ReferenceData(version="ref-synthetic-1", types=[existing])


def read_candidates(issue: Issue) -> list[DuplicateCandidate]:
    """Return an issue's candidates as the typed model."""
    entries = issue.details["candidates"]
    assert isinstance(entries, list)
    return [DuplicateCandidate.model_validate(entry) for entry in entries]


def test_exact_match_candidate_carries_reference_attributes(bundle: ConfigBundle) -> None:
    """EXISTS_IN_LABVANTAGE lists the existing type with its description, class and flag."""
    reference = make_described_reference("Syn A")
    result = run_validation(bundle, [make_record(bundle)], reference=reference)
    [issue] = issues_with_code(result, codes.EXISTS_IN_LABVANTAGE)
    [candidate] = read_candidates(issue)
    assert (candidate.description, candidate.consumable_class, candidate.active_flag) == (
        DESCRIPTION,
        CLASS,
        ACTIVE,
    )
    assert candidate.match == "exact"


def test_normalized_match_candidate_carries_reference_attributes(bundle: ConfigBundle) -> None:
    """POSSIBLE_DUPLICATE from a normalized match lists the attributes too."""
    reference = make_described_reference("SYN  a")
    result = run_validation(bundle, [make_record(bundle)], reference=reference)
    [issue] = issues_with_code(result, codes.POSSIBLE_DUPLICATE)
    [candidate] = read_candidates(issue)
    assert (candidate.match, candidate.description) == ("normalized", DESCRIPTION)


def test_judge_candidate_carries_reference_attributes(bundle: ConfigBundle) -> None:
    """A type the judge calls the same lists its attributes next to the judge's reason."""
    record = make_record(bundle, name="Syn Buffer 10uM")
    reference = make_described_reference("Syn Buffer 100uM")
    result = run_validation(bundle, [record], reference=reference, judge=FakeJudge("same"))
    [issue] = issues_with_code(result, codes.POSSIBLE_DUPLICATE)
    [candidate] = read_candidates(issue)
    assert (candidate.match, candidate.reason) == ("same", "synthetic")
    assert (candidate.description, candidate.consumable_class) == (DESCRIPTION, CLASS)


def test_missing_reference_attributes_are_null(bundle: ConfigBundle) -> None:
    """An existing type without description, class or flag gives None, never a made-up value."""
    reference = make_described_reference("Syn A", is_described=False)
    result = run_validation(bundle, [make_record(bundle)], reference=reference)
    [issue] = issues_with_code(result, codes.EXISTS_IN_LABVANTAGE)
    [candidate] = read_candidates(issue)
    assert (candidate.description, candidate.consumable_class, candidate.active_flag) == (
        None,
        None,
        None,
    )


def test_attributes_do_not_change_the_issue_id_or_accepted_state(bundle: ConfigBundle) -> None:
    """The issue ID is keyed on the name only; an accepted issue stays accepted with new details."""
    record = make_record(bundle)
    bare = run_validation(bundle, [record], reference=make_described_reference("Syn A", False))
    [before] = issues_with_code(bare, codes.EXISTS_IN_LABVANTAGE)
    name_key = find_name_rule(bundle.field_rules).key
    expected_id = make_issue_id(codes.EXISTS_IN_LABVANTAGE, record.record_id, name_key, "Syn A")
    assert before.issue_id == expected_id
    # The same issue, accepted earlier with details that had no attributes
    accepted = before.model_copy(update={"status": "accepted", "closed_by": "chg_0001"})
    described = run_validation(
        bundle,
        [record],
        reference=make_described_reference("Syn A"),
        previous_issues=[accepted],
    )
    [after] = [issue for issue in described.issues if issue.issue_id == expected_id]
    assert after.status == "accepted"
    assert read_candidates(after)[0].description == DESCRIPTION


def test_review_view_types_the_candidates(bundle: ConfigBundle) -> None:
    """The review view's issue summary lists the candidates with their attributes."""
    result = run_validation(
        bundle, [make_record(bundle)], reference=make_described_reference("Syn A")
    )
    view = build_review_view(result.records, result.issues, bundle.field_rules, [], [])
    name_key = find_name_rule(bundle.field_rules).key
    [cell] = [cell for cell in view.rows[0].cells if cell.field == name_key]
    [summary] = [i for i in cell.issues if i.code == codes.EXISTS_IN_LABVANTAGE]
    assert [c.description for c in summary.duplicate_candidates] == [DESCRIPTION]


def test_review_view_leaves_out_malformed_candidates() -> None:
    """A details entry without the candidate shape is left out of the summary."""
    good: dict[str, JsonValue] = {"candidate_id": "ref_0001", "name": "Syn A", "match": "exact"}
    entries: list[JsonValue] = [good, {"name": "no id"}, "text"]
    issue = Issue(
        issue_id="iss_x",
        code=codes.POSSIBLE_DUPLICATE,
        severity="warning",
        record_id="rec_0001",
        field=None,
        message="synthetic",
        details={"candidates": entries},
    )
    candidates = read_duplicate_candidates(issue)
    assert [(c.name, c.description) for c in candidates] == [("Syn A", None)]
