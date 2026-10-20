"""Review service tests: each change type, resend, rejected changes, undo, Verify and the label.

Synthetic records only; field keys and lookup values are read from the client config.
"""

from pathlib import Path

import pytest

from app.config.bundle import ConfigBundle
from app.config.field_rules import FieldRule
from app.contracts.changes import SetValueChange
from app.contracts.extraction import Alternative, Evidence, ExtractedField
from app.contracts.record import FieldVerification, StoredRecord
from app.contracts.verification import CitationCheck, MissedCandidate, VerificationOutput
from app.review.errors import ChangeRejectedError, RunNotInReviewError
from app.review.service import ReviewContext, verify_run
from app.transform.notes import TransformNote
from app.validation import codes
from app.validation.duplicates import find_name_rule
from app.validation.service import ProcessingFindings, ValidationConfig, make_validation_config
from tests.unit.review_helpers import (
    NOW,
    RUN_ID,
    USER,
    accept_warning,
    exclude_record,
    find_issues,
    make_context,
    make_relaxed_config,
    pick_alternative,
    read_record,
    recheck,
    restore_record,
    save,
    set_value,
    start_review,
    undo_bulk,
)
from tests.unit.validation_helpers import find_rule, make_record, set_output, update_field


@pytest.fixture
def config(bundle: ConfigBundle) -> ValidationConfig:
    """Return the run config with the workbook's impossible length limits dropped."""
    return make_relaxed_config(bundle)


@pytest.fixture
def context(config: ValidationConfig) -> ReviewContext:
    """Return a review context on the relaxed config."""
    return make_context(config)


def lookup_rule(config: ValidationConfig) -> FieldRule:
    """Return an optional lookup field with at least two list values."""
    return find_rule(
        config.field_rules,
        lambda rule: (
            rule.lookup_sheet is not None
            and rule.requirement == "optional"
            and len(config.lookup_lists.sheets[rule.lookup_sheet]) >= 2
        ),
    )


def text_rule(config: ValidationConfig) -> FieldRule:
    """Return a free-text field that is not the record name."""
    name_key = find_name_rule(config.field_rules).key
    return find_rule(
        config.field_rules,
        lambda rule: rule.type == "text" and rule.lookup_sheet is None and rule.key != name_key,
    )


def list_values(config: ValidationConfig, rule: FieldRule) -> list[str]:
    """Return the list values of a lookup field."""
    assert rule.lookup_sheet is not None
    return config.lookup_lists.sheets[rule.lookup_sheet]


def with_citation(record: StoredRecord, key: str, check: CitationCheck) -> StoredRecord:
    """Return the record with one field's citation check result replaced."""
    stored = record.fields[key]
    verification = FieldVerification(citation_check=check)
    return update_field(record, key, stored.model_copy(update={"verification": verification}))


def with_equivalent(record: StoredRecord, key: str) -> StoredRecord:
    """Return the record with one field marked "or equivalent" (raises OR_EQUIVALENT)."""
    stored = record.fields[key]
    assert stored.extraction is not None
    extraction = stored.extraction.model_copy(update={"allows_equivalent": True})
    return update_field(record, key, stored.model_copy(update={"extraction": extraction}))


# ----- set_value -----


def test_set_value_without_open_issue_needs_a_reason(
    tmp_path: Path, bundle: ConfigBundle, config: ValidationConfig, context: ReviewContext
) -> None:
    """Changing a value with no open issue is rejected without a reason and saved with one."""
    database = start_review(tmp_path, bundle, context, [make_record(bundle)])
    key = text_rule(config).key
    with pytest.raises(ChangeRejectedError):
        save(database, context, set_value("chg_0001", key, "synthetic new"))
    with pytest.raises(ChangeRejectedError):
        save(database, context, set_value("chg_0001", key, "synthetic new", reason="  "))
    result = save(database, context, set_value("chg_0001", key, "synthetic new", reason="typo"))
    assert result.saved_change_ids == ["chg_0001"]


def test_set_value_is_pending_until_recheck(
    tmp_path: Path, bundle: ConfigBundle, config: ValidationConfig, context: ReviewContext
) -> None:
    """A saved change does not touch the record until the re-check applies it."""
    database = start_review(tmp_path, bundle, context, [make_record(bundle)])
    key = text_rule(config).key
    save(database, context, set_value("chg_0001", key, "synthetic new", reason="typo"))
    assert read_record(database).fields[key].output.value != "synthetic new"
    result = recheck(database, context)
    output = read_record(database).fields[key].output
    assert (output.value, output.origin, output.changes) == ("synthetic new", "user_edited", [])
    assert result.applied_change_ids == ["chg_0001"]
    assert [row.stored.status for row in database.read_changes(RUN_ID)] == ["applied"]


def test_set_value_clears_transform_notes_and_resolves_their_issue(
    tmp_path: Path, bundle: ConfigBundle, config: ValidationConfig, context: ReviewContext
) -> None:
    """A new value drops the old FORMAT_CORRECTED note; its issue is resolved by the user."""
    rule = lookup_rule(config)
    first, second = list_values(config, rule)[:2]
    note = TransformNote(code="FORMAT_CORRECTED", original=first.lower(), value=first)
    record = set_output(make_record(bundle), rule.key, first, changes=[note.to_text()])
    database = start_review(tmp_path, bundle, context, [record])
    assert len(find_issues(database, codes.FORMAT_CORRECTED, "open")) == 1
    # The field has an open (grey) issue, so no reason is needed
    save(database, context, set_value("chg_0001", rule.key, second))
    recheck(database, context)
    resolved = find_issues(database, codes.FORMAT_CORRECTED)
    assert [(issue.status, issue.closed_by) for issue in resolved] == [("resolved", USER)]
    history = database.read_issue_history(RUN_ID)
    assert [
        (step.action, step.by) for step in history if step.issue_id == resolved[0].issue_id
    ] == [
        ("opened", None),
        ("resolved", USER),
    ]


def test_list_value_must_be_on_the_lookup_list(
    tmp_path: Path, bundle: ConfigBundle, config: ValidationConfig, context: ReviewContext
) -> None:
    """A list field only takes a value from the run's lookup list."""
    database = start_review(tmp_path, bundle, context, [make_record(bundle)])
    key = lookup_rule(config).key
    with pytest.raises(ChangeRejectedError):
        save(database, context, set_value("chg_0001", key, "synthetic not listed", reason="x"))


def test_blank_for_now_field_cannot_be_changed(
    tmp_path: Path, bundle: ConfigBundle, config: ValidationConfig, context: ReviewContext
) -> None:
    """Fields the tool does not fill are rejected (they are exported blank)."""
    database = start_review(tmp_path, bundle, context, [make_record(bundle)])
    key = next(rule.key for rule in config.field_rules.fields if rule.role == "blank_for_now")
    with pytest.raises(ChangeRejectedError):
        save(database, context, set_value("chg_0001", key, "synthetic", reason="x"))


# ----- pick_alternative -----


def make_conflict_record(bundle: ConfigBundle, rule: FieldRule, values: list[str]) -> StoredRecord:
    """Return a record whose field is conflicting between the given values (case changed)."""
    alternatives = [
        Alternative(value=value.lower(), evidence=[Evidence(chunk_id="doc01-c001", quote=value)])
        for value in values
    ]
    extraction = ExtractedField(status="conflicting", alternatives=alternatives, warning="x")
    record = set_output(make_record(bundle), rule.key, None)
    stored = record.fields[rule.key].model_copy(update={"extraction": extraction})
    return update_field(record, rule.key, stored)


def test_pick_alternative_uses_the_transformed_alternative(
    tmp_path: Path, bundle: ConfigBundle, config: ValidationConfig, context: ReviewContext
) -> None:
    """Picking an alternative formats it like an extracted value and resolves the conflict."""
    rule = lookup_rule(config)
    values = list_values(config, rule)[:2]
    database = start_review(tmp_path, bundle, context, [make_conflict_record(bundle, rule, values)])
    assert len(find_issues(database, codes.CONFLICT_UNRESOLVED, "open")) == 1
    save(database, context, pick_alternative("chg_0001", rule.key, 1))
    recheck(database, context)
    output = read_record(database).fields[rule.key].output
    assert (output.value, output.selected_alternative) == (values[1], 1)
    assert find_issues(database, codes.CONFLICT_UNRESOLVED, "open") == []


def test_pick_alternative_out_of_range_is_rejected(
    tmp_path: Path, bundle: ConfigBundle, config: ValidationConfig, context: ReviewContext
) -> None:
    """An index past the alternatives is rejected."""
    rule = lookup_rule(config)
    record = make_conflict_record(bundle, rule, list_values(config, rule)[:2])
    database = start_review(tmp_path, bundle, context, [record])
    with pytest.raises(ChangeRejectedError):
        save(database, context, pick_alternative("chg_0001", rule.key, 2))


# ----- accept_warning -----


def test_accept_warning_marks_it_accepted_by_the_user(
    tmp_path: Path, bundle: ConfigBundle, config: ValidationConfig, context: ReviewContext
) -> None:
    """An accepted warning stays accepted after the re-check, closed by the user."""
    record = with_equivalent(make_record(bundle), text_rule(config).key)
    database = start_review(tmp_path, bundle, context, [record])
    issue = find_issues(database, codes.OR_EQUIVALENT, "open")[0]
    save(database, context, accept_warning("chg_0001", issue.issue_id))
    recheck(database, context)
    accepted = find_issues(database, codes.OR_EQUIVALENT)[0]
    assert (accepted.status, accepted.closed_by) == ("accepted", USER)
    assert read_record(database).action_needed == "none"


def test_individual_review_accept_needs_the_source_viewed(
    tmp_path: Path, bundle: ConfigBundle, config: ValidationConfig, context: ReviewContext
) -> None:
    """An individual-review warning is accepted only after its source was opened."""
    record = with_citation(make_record(bundle), text_rule(config).key, "not_verified")
    database = start_review(tmp_path, bundle, context, [record])
    issue = find_issues(database, codes.CITATION_NOT_VERIFIED, "open")[0]
    with pytest.raises(ChangeRejectedError):
        save(database, context, accept_warning("chg_0001", issue.issue_id))
    save(database, context, accept_warning("chg_0001", issue.issue_id, source_viewed=True))
    recheck(database, context)
    assert find_issues(database, codes.CITATION_NOT_VERIFIED)[0].status == "accepted"


def test_bulk_accept_of_individual_review_issue_is_rejected(
    tmp_path: Path, bundle: ConfigBundle, config: ValidationConfig, context: ReviewContext
) -> None:
    """A bulk accept of an individual-review warning rejects the whole request."""
    record = with_citation(make_record(bundle), text_rule(config).key, "not_verified")
    database = start_review(tmp_path, bundle, context, [record])
    issue = find_issues(database, codes.CITATION_NOT_VERIFIED, "open")[0]
    bulk_accept = accept_warning("chg_0002", issue.issue_id, source_viewed=True, bulk_id="blk_1")
    other = exclude_record("chg_0001", "rec_0001", "synthetic reason")
    with pytest.raises(ChangeRejectedError) as error:
        save(database, context, other, bulk_accept)
    assert error.value.code == "BULK_ACCEPT_NOT_ALLOWED"
    assert database.read_changes(RUN_ID) == []


def test_note_required_accept_needs_a_note(
    tmp_path: Path, bundle: ConfigBundle, context: ReviewContext
) -> None:
    """A run issue whose catalogue entry needs a note is accepted only with one."""
    verification = VerificationOutput(
        field_findings=[],
        record_findings=[],
        missed_candidates=[MissedCandidate(name_as_written="Syn X", sources=[], reason="x")],
        excluded_item_challenges=[],
        unreported_conflicts=[],
    )
    findings = ProcessingFindings(verification=verification)
    database = start_review(tmp_path, bundle, context, [make_record(bundle)], findings)
    issue = find_issues(database, codes.MISSED_CANDIDATES_UNRESOLVED, "open")[0]
    with pytest.raises(ChangeRejectedError):
        save(database, context, accept_warning("chg_0001", issue.issue_id, source_viewed=True))
    accept = accept_warning("chg_0001", issue.issue_id, source_viewed=True, note="Added by hand")
    save(database, context, accept)
    recheck(database, context)
    # The stored findings raise the same issue again on re-check; it keeps its accepted state
    assert find_issues(database, codes.MISSED_CANDIDATES_UNRESOLVED)[0].status == "accepted"
    notes = [step.note for step in database.read_issue_history(RUN_ID) if step.action == "accepted"]
    assert notes == ["Added by hand"]


def test_error_cannot_be_accepted(
    tmp_path: Path, bundle: ConfigBundle, context: ReviewContext
) -> None:
    """Only warnings can be accepted; a red issue must be fixed."""
    strict = make_context(make_validation_config(bundle))
    database = start_review(tmp_path, bundle, strict, [make_record(bundle)])
    issue = find_issues(database, codes.TOO_LONG, "open")[0]
    with pytest.raises(ChangeRejectedError):
        save(database, strict, accept_warning("chg_0001", issue.issue_id))


# ----- exclude and restore -----


def test_exclude_and_restore_a_record(
    tmp_path: Path, bundle: ConfigBundle, context: ReviewContext
) -> None:
    """Excluding sets who, when and why plus an audit event; restoring removes the exclusion."""
    database = start_review(tmp_path, bundle, context, [make_record(bundle)])
    save(database, context, exclude_record("chg_0001", "rec_0001", "Equipment"))
    recheck(database, context)
    record = read_record(database)
    assert record.exclusion is not None and record.exclusion.reason == "Equipment"
    assert (record.exclusion.by, record.action_needed) == (USER, "excluded")
    save(database, context, restore_record("chg_0002", "rec_0001"))
    recheck(database, context)
    assert read_record(database).exclusion is None
    events = [event.event for event in database.read_audit_events(RUN_ID)]
    assert events == ["record_excluded", "record_restored"]


def test_exclude_needs_a_reason(
    tmp_path: Path, bundle: ConfigBundle, context: ReviewContext
) -> None:
    """A blank exclusion reason is rejected."""
    database = start_review(tmp_path, bundle, context, [make_record(bundle)])
    with pytest.raises(ChangeRejectedError):
        save(database, context, exclude_record("chg_0001", "rec_0001", "   "))


def test_unknown_record_is_rejected(
    tmp_path: Path, bundle: ConfigBundle, context: ReviewContext
) -> None:
    """A change to a record that is not in the run is rejected."""
    database = start_review(tmp_path, bundle, context, [make_record(bundle)])
    with pytest.raises(ChangeRejectedError):
        save(database, context, restore_record("chg_0001", "rec_0099"))


# ----- resend and run status -----


def test_resent_change_is_ignored(
    tmp_path: Path, bundle: ConfigBundle, context: ReviewContext
) -> None:
    """A change whose change_id is already stored is ignored, also within one request."""
    database = start_review(tmp_path, bundle, context, [make_record(bundle)])
    change = exclude_record("chg_0001", "rec_0001", "Equipment")
    first = save(database, context, change, change)
    second = save(database, context, change)
    assert (first.saved_change_ids, first.ignored_change_ids) == (["chg_0001"], ["chg_0001"])
    assert (second.saved_change_ids, second.ignored_change_ids) == ([], ["chg_0001"])
    assert len(database.read_changes(RUN_ID)) == 1


def test_changes_are_rejected_when_run_is_not_in_review(
    tmp_path: Path, bundle: ConfigBundle, context: ReviewContext
) -> None:
    """A run that is not in review cannot be changed or re-checked."""
    database = start_review(tmp_path, bundle, context, [make_record(bundle)])
    database.set_run_status(RUN_ID, "failed")
    with pytest.raises(RunNotInReviewError):
        save(database, context, exclude_record("chg_0001", "rec_0001", "Equipment"))
    with pytest.raises(RunNotInReviewError):
        recheck(database, context)


# ----- undo bulk -----


def make_two_records(bundle: ConfigBundle) -> list[StoredRecord]:
    """Return two synthetic records with different names."""
    return [make_record(bundle, "rec_0001", "Syn A"), make_record(bundle, "rec_0002", "Syn B")]


def bulk_set(field: str, value: str, bulk_id: str, first_id: int) -> list[SetValueChange]:
    """Return a set_value change per record, sharing one bulk ID."""
    return [
        set_value(
            f"chg_{first_id + n:04d}", field, value, record_id, reason="bulk", bulk_id=bulk_id
        )
        for n, record_id in enumerate(("rec_0001", "rec_0002"))
    ]


def test_undo_bulk_puts_every_value_back(
    tmp_path: Path, bundle: ConfigBundle, config: ValidationConfig, context: ReviewContext
) -> None:
    """Undoing a bulk change restores each record's earlier output and logs one event."""
    key = text_rule(config).key
    database = start_review(tmp_path, bundle, context, make_two_records(bundle))
    original = read_record(database).fields[key].output
    save(database, context, *bulk_set(key, "synthetic bulk", "blk_0001", 1))
    recheck(database, context)
    assert read_record(database, "rec_0002").fields[key].output.value == "synthetic bulk"
    save(database, context, undo_bulk("chg_0003", "blk_0001"))
    recheck(database, context)
    for record_id in ("rec_0001", "rec_0002"):
        assert read_record(database, record_id).fields[key].output == original
    undone = [row.undone_by for row in database.read_changes(RUN_ID)][:2]
    assert undone == ["chg_0003", "chg_0003"]
    assert [event.event for event in database.read_audit_events(RUN_ID)] == ["bulk_undone"]


def test_undo_bulk_keeps_a_later_change(
    tmp_path: Path, bundle: ConfigBundle, config: ValidationConfig, context: ReviewContext
) -> None:
    """A value changed again after the bulk action keeps the later change."""
    key = text_rule(config).key
    database = start_review(tmp_path, bundle, context, make_two_records(bundle))
    original = read_record(database).fields[key].output
    later = set_value("chg_0003", key, "synthetic later", "rec_0002", reason="later")
    save(database, context, *bulk_set(key, "synthetic bulk", "blk_0001", 1), later)
    save(database, context, undo_bulk("chg_0004", "blk_0001"))
    recheck(database, context)
    assert read_record(database, "rec_0001").fields[key].output == original
    assert read_record(database, "rec_0002").fields[key].output.value == "synthetic later"


def test_undo_of_unknown_or_undone_bulk_is_rejected(
    tmp_path: Path, bundle: ConfigBundle, config: ValidationConfig, context: ReviewContext
) -> None:
    """Undo needs an existing bulk action that was not undone already."""
    key = text_rule(config).key
    database = start_review(tmp_path, bundle, context, make_two_records(bundle))
    with pytest.raises(ChangeRejectedError):
        save(database, context, undo_bulk("chg_0001", "blk_0001"))
    save(database, context, *bulk_set(key, "synthetic bulk", "blk_0001", 1))
    save(database, context, undo_bulk("chg_0003", "blk_0001"))
    with pytest.raises(ChangeRejectedError):
        save(database, context, undo_bulk("chg_0004", "blk_0001"))


def test_undo_bulk_reopens_accepted_warnings(
    tmp_path: Path, bundle: ConfigBundle, config: ValidationConfig, context: ReviewContext
) -> None:
    """Undoing an "accept all of this type" bulk action opens the warnings again."""
    key = text_rule(config).key
    records = [with_equivalent(record, key) for record in make_two_records(bundle)]
    database = start_review(tmp_path, bundle, context, records)
    issues = find_issues(database, codes.OR_EQUIVALENT, "open")
    accepts = [
        accept_warning(f"chg_{n:04d}", issue.issue_id, bulk_id="blk_0001")
        for n, issue in enumerate(issues, start=1)
    ]
    save(database, context, *accepts)
    recheck(database, context)
    assert len(find_issues(database, codes.OR_EQUIVALENT, "accepted")) == 2
    save(database, context, undo_bulk("chg_0003", "blk_0001"))
    recheck(database, context)
    assert len(find_issues(database, codes.OR_EQUIVALENT, "open")) == 2


# ----- Verify and the verified label -----


def test_verify_is_blocked_by_a_red_issue(tmp_path: Path, bundle: ConfigBundle) -> None:
    """With the literal workbook limits every record is red, so Verify is blocked."""
    strict = make_context(make_validation_config(bundle))
    database = start_review(tmp_path, bundle, strict, [make_record(bundle)])
    result = verify_run(database, strict, RUN_ID, USER, NOW)
    assert not result.is_verified
    assert [issue.code for issue in result.blocking_errors] == [codes.TOO_LONG]
    assert not database.read_run(RUN_ID).is_verified


def test_verify_is_blocked_by_an_individual_review_warning(
    tmp_path: Path, bundle: ConfigBundle, config: ValidationConfig, context: ReviewContext
) -> None:
    """An open individual-review warning blocks Verify and is never accepted by it."""
    record = with_citation(make_record(bundle), text_rule(config).key, "not_verified")
    database = start_review(tmp_path, bundle, context, [record])
    result = verify_run(database, context, RUN_ID, USER, NOW)
    assert not result.is_verified
    assert [i.code for i in result.individual_review_warnings] == [codes.CITATION_NOT_VERIFIED]
    assert find_issues(database, codes.CITATION_NOT_VERIFIED)[0].status == "open"


def test_verify_accepts_other_warnings_and_sets_the_label(
    tmp_path: Path, bundle: ConfigBundle, config: ValidationConfig, context: ReviewContext
) -> None:
    """With only ordinary warnings left, Verify accepts them for the user and sets the label."""
    record = with_equivalent(make_record(bundle), text_rule(config).key)
    database = start_review(tmp_path, bundle, context, [record])
    result = verify_run(database, context, RUN_ID, USER, NOW)
    assert result.is_verified
    assert [issue.code for issue in result.accepted_warnings] == [codes.OR_EQUIVALENT]
    issue = find_issues(database, codes.OR_EQUIVALENT)[0]
    assert (issue.status, issue.closed_by) == ("accepted", USER)
    run = database.read_run(RUN_ID)
    assert (run.is_verified, run.verified_by, run.verified_at) == (True, USER, NOW)
    assert read_record(database).action_needed == "none"
    assert [event.event for event in database.read_audit_events(RUN_ID)] == ["run_verified"]


def test_verify_ignores_issues_of_excluded_records(
    tmp_path: Path, bundle: ConfigBundle, config: ValidationConfig, context: ReviewContext
) -> None:
    """An excluded record's blocking issues do not block Verify."""
    records = make_two_records(bundle)
    records[1] = with_citation(records[1], text_rule(config).key, "not_verified")
    database = start_review(tmp_path, bundle, context, records)
    save(database, context, exclude_record("chg_0001", "rec_0002", "Equipment"))
    assert verify_run(database, context, RUN_ID, USER, NOW).is_verified


def test_a_later_change_removes_the_verified_label(
    tmp_path: Path, bundle: ConfigBundle, context: ReviewContext
) -> None:
    """Saving any change after Verify removes the label, with an audit event."""
    database = start_review(tmp_path, bundle, context, [make_record(bundle)])
    assert verify_run(database, context, RUN_ID, USER, NOW).is_verified
    save(database, context, exclude_record("chg_0001", "rec_0001", "Equipment"))
    run = database.read_run(RUN_ID)
    assert (run.is_verified, run.verified_by, run.verified_at) == (False, None, None)
    events = [event.event for event in database.read_audit_events(RUN_ID)]
    assert events == ["run_verified", "verified_label_removed"]


def test_resent_change_keeps_the_label(
    tmp_path: Path, bundle: ConfigBundle, context: ReviewContext
) -> None:
    """A resent (ignored) change is not a new change, so the label stays."""
    database = start_review(tmp_path, bundle, context, [make_record(bundle)])
    change = exclude_record("chg_0001", "rec_0001", "Equipment")
    save(database, context, change)
    assert verify_run(database, context, RUN_ID, USER, NOW).is_verified
    save(database, context, change)
    assert database.read_run(RUN_ID).is_verified
