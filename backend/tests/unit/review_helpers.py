"""Shared helpers for review tests: a review database with a run in review, and change builders.

Records are synthetic (from `validation_helpers.py`); field keys and values come from the config.
"""

from datetime import UTC, datetime
from pathlib import Path

from app.config.bundle import ConfigBundle
from app.config.field_rules import FieldRule
from app.contracts.changes import (
    AcceptWarningChange,
    Change,
    ExcludeRecordChange,
    PickAlternativeChange,
    RestoreRecordChange,
    SetValueChange,
    UndoBulkChange,
)
from app.contracts.issue import Issue
from app.contracts.record import StoredRecord
from app.contracts.run import RunInfo
from app.review.service import RecheckResult, ReviewContext, SaveResult, recheck_run, save_changes
from app.storage.review_db import ReviewDatabase
from app.validation.judge_cache import InMemoryJudgeCache, JudgeRunner
from app.validation.service import (
    ProcessingFindings,
    ValidationConfig,
    make_validation_config,
    validate_run,
)
from tests.unit.validation_helpers import EMPTY_REFERENCE, JUDGE_PROMPT_VERSION, FakeJudge

RUN_ID = "run_0001"
USER = "synthetic.user"
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


def make_relaxed_config(bundle: ConfigBundle) -> ValidationConfig:
    """Return the run config without length limits no list value can meet.

    The workbook gives Container Tracking Method a 1-character limit and longer values, so every
    record is red (as documented). Tests that need a clean record drop such limits here.
    """
    config = make_validation_config(bundle)
    rules = [relax_rule(rule, bundle) for rule in config.field_rules.fields]
    field_rules = config.field_rules.model_copy(update={"fields": rules})
    return config.model_copy(update={"field_rules": field_rules})


def relax_rule(rule: FieldRule, bundle: ConfigBundle) -> FieldRule:
    """Drop a lookup field's length limit when none of its list values fits it."""
    if rule.lookup_sheet is None or rule.max_length is None:
        return rule
    values = bundle.lookup_lists.sheets[rule.lookup_sheet]
    if any(len(value) <= rule.max_length for value in values):
        return rule
    return rule.model_copy(update={"max_length": None})


def make_context(config: ValidationConfig, judge: FakeJudge | None = None) -> ReviewContext:
    """Return a review context with a fake judge and empty reference data."""
    return ReviewContext(
        config=config,
        judge=judge or FakeJudge(),
        judge_cache=InMemoryJudgeCache(),
        judge_prompt_version=JUDGE_PROMPT_VERSION,
        judge_call_limit=None,
        reference=EMPTY_REFERENCE,
    )


def start_review(
    tmp_path: Path,
    bundle: ConfigBundle,
    context: ReviewContext,
    records: list[StoredRecord],
    findings: ProcessingFindings | None = None,
) -> ReviewDatabase:
    """Create a review database holding one run in review, as the graph would leave it."""
    database = ReviewDatabase(tmp_path / "review.sqlite")
    database.add_run(
        RunInfo(
            run_id=RUN_ID,
            name="synthetic run",
            created_by=USER,
            created_at=NOW,
            config_versions=bundle.versions(),
            status="validating",
        )
    )
    findings = findings or ProcessingFindings()
    runner = JudgeRunner(context.judge, context.judge_cache, JUDGE_PROMPT_VERSION, None)
    result = validate_run(records, context.config, runner, context.reference, findings)
    database.save_processing_result(RUN_ID, result.records, result.issues, findings, [], NOW)
    database.set_run_status(RUN_ID, "in_review")
    return database


def save(database: ReviewDatabase, context: ReviewContext, *changes: Change) -> SaveResult:
    """Save changes for the test user."""
    return save_changes(database, context, RUN_ID, list(changes), USER, NOW)


def recheck(database: ReviewDatabase, context: ReviewContext) -> RecheckResult:
    """Re-check the run for the test user."""
    return recheck_run(database, context, RUN_ID, USER, NOW)


def read_record(database: ReviewDatabase, record_id: str = "rec_0001") -> StoredRecord:
    """Return one stored record."""
    return next(r for r in database.read_records(RUN_ID) if r.record_id == record_id)


def find_issues(database: ReviewDatabase, code: str, status: str | None = None) -> list[Issue]:
    """Return the stored issues with one code (and status, when given)."""
    return [
        issue
        for issue in database.read_issues(RUN_ID)
        if issue.code == code and (status is None or issue.status == status)
    ]


def set_value(
    change_id: str,
    field: str,
    value: str | None,
    record_id: str = "rec_0001",
    reason: str | None = None,
    bulk_id: str | None = None,
) -> SetValueChange:
    """Build a set_value change."""
    return SetValueChange(
        type="set_value",
        change_id=change_id,
        record_id=record_id,
        field=field,
        value=value,
        reason=reason,
        bulk_id=bulk_id,
    )


def pick_alternative(change_id: str, field: str, index: int) -> PickAlternativeChange:
    """Build a pick_alternative change on the first record."""
    return PickAlternativeChange(
        type="pick_alternative",
        change_id=change_id,
        record_id="rec_0001",
        field=field,
        alternative_index=index,
    )


def accept_warning(
    change_id: str,
    issue_id: str,
    source_viewed: bool = False,
    note: str | None = None,
    bulk_id: str | None = None,
) -> AcceptWarningChange:
    """Build an accept_warning change."""
    return AcceptWarningChange(
        type="accept_warning",
        change_id=change_id,
        issue_id=issue_id,
        source_viewed=source_viewed,
        note=note,
        bulk_id=bulk_id,
    )


def exclude_record(change_id: str, record_id: str, reason: str) -> ExcludeRecordChange:
    """Build an exclude_record change."""
    return ExcludeRecordChange(
        type="exclude_record", change_id=change_id, record_id=record_id, reason=reason
    )


def restore_record(change_id: str, record_id: str) -> RestoreRecordChange:
    """Build a restore_record change."""
    return RestoreRecordChange(type="restore_record", change_id=change_id, record_id=record_id)


def undo_bulk(change_id: str, bulk_id: str) -> UndoBulkChange:
    """Build an undo_bulk change."""
    return UndoBulkChange(type="undo_bulk", change_id=change_id, bulk_id=bulk_id)
