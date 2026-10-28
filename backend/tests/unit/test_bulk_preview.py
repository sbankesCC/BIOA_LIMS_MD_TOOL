"""Bulk preview tests: the four modes (change all, fill missing, accept type, resolve conflicts).

Records are synthetic; field keys come from the client config, never written here.
"""

from datetime import UTC, datetime

import pytest

from app.config.bundle import ConfigBundle
from app.config.field_rules import FieldRule
from app.contracts.extraction import Alternative, ExtractedField
from app.contracts.issue import Issue, IssueSeverity
from app.contracts.record import Exclusion, FieldOutput, StoredRecord
from app.review.bulk_preview import BulkMode, BulkPreview, BulkRequest, find_bulk_matches
from app.review.errors import ReviewError
from tests.unit.validation_helpers import find_rule, make_record, set_output, update_field

WARNING_CODE = "SYNTHETIC_WARNING"
OTHER_CODE = "SYNTHETIC_OTHER"
EXCLUSION = Exclusion(
    by="synthetic.user", at=datetime(2026, 10, 20, tzinfo=UTC), reason="synthetic"
)


def text_rule(bundle: ConfigBundle) -> FieldRule:
    """Return an extracted single-value text field without a lookup list (not the name)."""
    return find_rule(
        bundle.field_rules,
        lambda rule: (
            rule.type == "text"
            and rule.lookup_sheet is None
            and not rule.multi_value
            and not rule.is_record_name
        ),
    )


def make_issue(
    record_id: str | None,
    field: str | None,
    code: str = WARNING_CODE,
    severity: IssueSeverity = "warning",
    individual_review: bool = False,
) -> Issue:
    """Return an open synthetic issue on one record's field."""
    return Issue(
        issue_id=f"iss_{record_id}_{field}_{code}",
        code=code,
        severity=severity,
        record_id=record_id,
        field=field,
        message="synthetic message",
        individual_review=individual_review,
    )


def exclude(record: StoredRecord) -> StoredRecord:
    """Return the record excluded."""
    return record.model_copy(update={"exclusion": EXCLUSION})


def make_conflict(record: StoredRecord, field: str, values: list[str]) -> StoredRecord:
    """Return the record with an unresolved conflict on one field, alternatives in this order."""
    extraction = ExtractedField(
        status="conflicting",
        alternatives=[Alternative(value=value, evidence=[]) for value in values],
    )
    stored = record.fields[field].model_copy(
        update={"extraction": extraction, "output": FieldOutput(value=None, origin="extracted")}
    )
    return update_field(record, field, stored)


def preview(
    bundle: ConfigBundle,
    records: list[StoredRecord],
    issues: list[Issue],
    mode: BulkMode,
    **values: object,
) -> BulkPreview:
    """Run the bulk preview for one mode with the given request values."""
    request = BulkRequest.model_validate({"mode": mode, **values})
    return find_bulk_matches(records, issues, request, bundle.field_rules)


def matched_ids(result: BulkPreview) -> list[str]:
    """Return the matched record IDs in order."""
    return [match.record_id for match in result.matches]


# ----- Change all -----


def test_change_all_matches_same_code_field_and_value_of_included_records(
    bundle: ConfigBundle,
) -> None:
    """Records with the same issue on the same field and value match; excluded ones never do."""
    key = text_rule(bundle).key
    records = [
        set_output(make_record(bundle, "rec_0001"), key, "synthetic a"),
        set_output(make_record(bundle, "rec_0002"), key, "synthetic a"),
        set_output(make_record(bundle, "rec_0003"), key, "synthetic b"),
        exclude(set_output(make_record(bundle, "rec_0004"), key, "synthetic a")),
    ]
    issues = [make_issue(record.record_id, key) for record in records]
    result = preview(bundle, records, issues, "change_all", issue_id=issues[0].issue_id)
    assert matched_ids(result) == ["rec_0001", "rec_0002"]
    assert result.count == 2
    assert result.value == "synthetic a"
    assert [match.value for match in result.matches] == ["synthetic a", "synthetic a"]


def test_change_all_without_an_issue_is_refused(bundle: ConfigBundle) -> None:
    """A mode that starts from an issue needs its issue_id."""
    with pytest.raises(ReviewError) as caught:
        preview(bundle, [make_record(bundle)], [], "change_all")
    assert caught.value.code == "BULK_NOT_POSSIBLE"


# ----- Fill missing -----


def test_fill_missing_matches_empty_values_but_not_conflicts_or_excluded(
    bundle: ConfigBundle,
) -> None:
    """Missing (null or blank) values match; filled, conflicting and excluded records do not."""
    key = text_rule(bundle).key
    records = [
        set_output(make_record(bundle, "rec_0001"), key, None),
        set_output(make_record(bundle, "rec_0002"), key, " "),
        make_record(bundle, "rec_0003"),
        exclude(set_output(make_record(bundle, "rec_0004"), key, None)),
        make_conflict(make_record(bundle, "rec_0005"), key, ["synthetic a", "synthetic b"]),
    ]
    issues = [make_issue("rec_0001", key)]
    result = preview(bundle, records, issues, "fill_missing", field=key)
    assert matched_ids(result) == ["rec_0001", "rec_0002"]
    assert [match.issue_id for match in result.matches] == [issues[0].issue_id, None]
    assert (result.field, result.count) == (key, 2)


def test_fill_missing_refuses_a_field_review_cannot_fill(bundle: ConfigBundle) -> None:
    """Only extracted fields can be filled; a placeholder or system field is refused."""
    rule = next(rule for rule in bundle.field_rules.fields if rule.role != "extracted")
    with pytest.raises(ReviewError) as caught:
        preview(bundle, [make_record(bundle)], [], "fill_missing", field=rule.key)
    assert caught.value.code == "BULK_NOT_POSSIBLE"


# ----- Accept all of a type -----


def test_accept_type_matches_open_warnings_of_the_code_on_any_field(
    bundle: ConfigBundle,
) -> None:
    """Warnings of the same code match on any field and on the record; excluded ones never."""
    key = text_rule(bundle).key
    name_key = bundle.field_rules.record_name_field().key
    records = [make_record(bundle, f"rec_000{n}") for n in (1, 2, 3)]
    records.append(exclude(make_record(bundle, "rec_0004")))
    accepted = make_issue("rec_0002", key).model_copy(update={"status": "accepted"})
    issues = [
        make_issue("rec_0001", key),
        make_issue("rec_0002", name_key),
        make_issue("rec_0003", None),
        make_issue("rec_0003", key, code=OTHER_CODE),
        make_issue("rec_0004", key),
        accepted.model_copy(update={"issue_id": "iss_accepted"}),
    ]
    result = preview(bundle, records, issues, "accept_type", issue_id=issues[0].issue_id)
    assert matched_ids(result) == ["rec_0001", "rec_0002", "rec_0003"]
    assert [match.issue_id for match in result.matches] == [i.issue_id for i in issues[:3]]


def test_accept_type_refuses_an_individual_review_warning(bundle: ConfigBundle) -> None:
    """An individual-review warning is never accepted in bulk (409)."""
    key = text_rule(bundle).key
    issue = make_issue("rec_0001", key, individual_review=True)
    with pytest.raises(ReviewError) as caught:
        preview(bundle, [make_record(bundle)], [issue], "accept_type", issue_id=issue.issue_id)
    assert caught.value.code == "BULK_ACCEPT_NOT_ALLOWED"


def test_accept_type_refuses_an_error(bundle: ConfigBundle) -> None:
    """A red issue cannot be accepted, so it has no bulk accept (400)."""
    key = text_rule(bundle).key
    issue = make_issue("rec_0001", key, severity="error")
    with pytest.raises(ReviewError) as caught:
        preview(bundle, [make_record(bundle)], [issue], "accept_type", issue_id=issue.issue_id)
    assert caught.value.code == "BULK_NOT_POSSIBLE"


# ----- Resolve repeated conflicts -----


def test_resolve_conflicts_gives_each_record_its_own_alternative_index(
    bundle: ConfigBundle,
) -> None:
    """The same set of alternatives in any order matches, with the chosen value's own index."""
    key = text_rule(bundle).key
    records = [
        make_conflict(make_record(bundle, "rec_0001"), key, ["synthetic a", "synthetic b"]),
        make_conflict(make_record(bundle, "rec_0002"), key, ["synthetic b", "synthetic a"]),
        make_conflict(make_record(bundle, "rec_0003"), key, ["synthetic a", "synthetic c"]),
        exclude(
            make_conflict(make_record(bundle, "rec_0004"), key, ["synthetic b", "synthetic a"])
        ),
    ]
    issues = [make_issue(record.record_id, key) for record in records]
    result = preview(
        bundle,
        records,
        issues,
        "resolve_conflicts",
        issue_id=issues[0].issue_id,
        alternative_index=1,
    )
    assert matched_ids(result) == ["rec_0001", "rec_0002"]
    assert [match.alternative_index for match in result.matches] == [1, 0]
    assert result.count == 2


def test_resolve_conflicts_refuses_an_index_outside_the_alternatives(
    bundle: ConfigBundle,
) -> None:
    """The chosen index must be one of the selected conflict's alternatives."""
    key = text_rule(bundle).key
    record = make_conflict(make_record(bundle), key, ["synthetic a", "synthetic b"])
    issue = make_issue(record.record_id, key)
    with pytest.raises(ReviewError) as caught:
        preview(
            bundle,
            [record],
            [issue],
            "resolve_conflicts",
            issue_id=issue.issue_id,
            alternative_index=2,
        )
    assert caught.value.code == "BULK_NOT_POSSIBLE"


def test_resolve_conflicts_needs_the_chosen_alternative(bundle: ConfigBundle) -> None:
    """Without alternative_index there is nothing to apply to the other conflicts."""
    key = text_rule(bundle).key
    record = make_conflict(make_record(bundle), key, ["synthetic a", "synthetic b"])
    issue = make_issue(record.record_id, key)
    with pytest.raises(ReviewError) as caught:
        preview(bundle, [record], [issue], "resolve_conflicts", issue_id=issue.issue_id)
    assert caught.value.code == "BULK_NOT_POSSIBLE"
