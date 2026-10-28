"""Validation service (ARCHITECTURE §4.8): finds every issue in a run's records.

Called by the graph at the end of processing and by the review service on re-check and Verify.
It reports issues and writes only the validation section (`issue_ids`, `action_needed`); it
never changes a value. Excluded records are skipped and keep their earlier issues.
"""

from collections.abc import Sequence

from pydantic import BaseModel

from app.config.bundle import ConfigBundle
from app.config.field_rules import FieldRules
from app.config.issue_catalogue import IssueCatalogue
from app.config.lookup_lists import LookupLists
from app.config.reference_mapping import ReferenceRules
from app.contracts.extraction import ExcludedItem
from app.contracts.issue import Issue
from app.contracts.record import StoredField, StoredRecord
from app.contracts.reference import ReferenceData
from app.contracts.verification import VerificationOutput
from app.validation import codes
from app.validation.action_needed import compute_action_needed
from app.validation.conditions import check_conditions
from app.validation.duplicates import check_reference, find_name_rule, find_run_duplicates
from app.validation.field_checks import check_field, is_checked_field
from app.validation.findings_to_issues import (
    find_field_finding_issues,
    find_or_equivalent_issue,
    find_record_finding_issues,
    find_run_finding_issues,
    find_unreported_conflict_issues,
)
from app.validation.issues import IssueDraft, make_issue
from app.validation.judge_cache import JudgeRunner
from app.validation.lifecycle import merge_issues


class ValidationConfig(BaseModel):
    """The config a run validates with: the versions captured at its start."""

    field_rules: FieldRules
    issue_catalogue: IssueCatalogue
    lookup_lists: LookupLists
    reference_rules: ReferenceRules


class ProcessingFindings(BaseModel):
    """What processing found that is not stored in the records themselves.

    `verification` gives unreported conflicts, missed candidates and challenged excluded items;
    `dropped_record_ids` are records a re-extraction did not return; `excluded_items` (from
    extraction) give the chunks of challenged excluded items.
    """

    verification: VerificationOutput | None = None
    dropped_record_ids: list[str] = []
    excluded_items: list[ExcludedItem] = []


class ValidationResult(BaseModel):
    """The records with their issue IDs and action needed, every issue, and judge calls made."""

    records: list[StoredRecord]
    issues: list[Issue]
    judge_calls_made: int


def make_validation_config(
    bundle: ConfigBundle, lookup_lists: LookupLists | None = None
) -> ValidationConfig:
    """Build the validation config from a bundle; a run may use its own lookup list version."""
    return ValidationConfig(
        field_rules=bundle.field_rules,
        issue_catalogue=bundle.issue_catalogue,
        lookup_lists=lookup_lists or bundle.lookup_lists,
        reference_rules=bundle.reference_mapping.rules,
    )


def validate_run(
    records: Sequence[StoredRecord],
    config: ValidationConfig,
    runner: JudgeRunner,
    reference: ReferenceData | None,
    findings: ProcessingFindings | None = None,
    previous_issues: Sequence[Issue] = (),
) -> ValidationResult:
    """Validate every record of a run and merge the issues with the earlier ones."""
    findings = findings or ProcessingFindings()
    active = [record for record in records if record.exclusion is None]
    skipped_ids = {record.record_id for record in records if record.exclusion is not None}
    # Find this pass's problems, then give them their catalogue form and stable IDs
    drafts = find_record_drafts(active, config, findings)
    drafts += find_run_drafts(active, config, runner, reference, findings)
    found = make_unique_issues(drafts, config)
    owned_codes = find_owned_codes(config.field_rules)
    issues = merge_issues(previous_issues, found, owned_codes, skipped_ids)
    # Only the validation section of each record changes
    updated = [attach_issues(record, issues) for record in records]
    return ValidationResult(records=updated, issues=issues, judge_calls_made=runner.calls_made)


def find_record_drafts(
    records: Sequence[StoredRecord], config: ValidationConfig, findings: ProcessingFindings
) -> list[IssueDraft]:
    """Return the problems found on each record on its own."""
    run_record_ids = {record.record_id for record in records}
    dropped_ids = set(findings.dropped_record_ids)
    drafts: list[IssueDraft] = []
    for record in records:
        drafts += find_field_drafts(record, config)
        drafts += check_conditions(record, config.field_rules)
        drafts += find_or_equivalent_issue(record)
        drafts += find_unreported_conflict_issues(record, findings.verification)
        drafts += find_record_finding_issues(record, run_record_ids, dropped_ids)
    return drafts


def find_field_drafts(record: StoredRecord, config: ValidationConfig) -> list[IssueDraft]:
    """Return the field checks and field findings of every checked field of a record."""
    drafts: list[IssueDraft] = []
    for rule in config.field_rules.fields:
        stored = record.fields.get(rule.key)
        # Fields the tool does not fill (blank_for_now, system) are not validated
        if stored is None or not is_checked_field(rule):
            continue
        drafts += check_field(record.record_id, rule, stored, config.lookup_lists)
        drafts += find_field_finding_issues(record.record_id, rule, stored)
    return drafts


def find_run_drafts(
    records: Sequence[StoredRecord],
    config: ValidationConfig,
    runner: JudgeRunner,
    reference: ReferenceData | None,
    findings: ProcessingFindings,
) -> list[IssueDraft]:
    """Return the problems that compare records: duplicates, plus run-level findings."""
    name_rule = find_name_rule(config.field_rules)
    drafts = find_run_duplicates(records, name_rule)
    drafts += find_reference_drafts(records, config, runner, reference)
    drafts += find_run_finding_issues(findings.verification, findings.excluded_items)
    return drafts


def find_reference_drafts(
    records: Sequence[StoredRecord],
    config: ValidationConfig,
    runner: JudgeRunner,
    reference: ReferenceData | None,
) -> list[IssueDraft]:
    """Check every record against the existing Consumable Types, if any were uploaded."""
    if reference is None:
        return [IssueDraft(code=codes.REFERENCE_DATA_MISSING)]
    drafts: list[IssueDraft] = []
    skipped_count = 0
    for record in records:
        check = check_reference(
            record, config.field_rules, reference, config.reference_rules, runner
        )
        drafts += check.drafts
        skipped_count += 1 if check.is_judge_skipped else 0
    # One run issue counts the records the call limit left unchecked
    if skipped_count:
        drafts.append(
            IssueDraft(
                code=codes.DUPLICATE_CHECK_SKIPPED,
                message_values={"count": str(skipped_count)},
                details={"count": skipped_count},
            )
        )
    return drafts


def make_unique_issues(drafts: Sequence[IssueDraft], config: ValidationConfig) -> list[Issue]:
    """Turn drafts into issues; two checks finding the same key give one issue (the first)."""
    issues: dict[str, Issue] = {}
    for draft in drafts:
        issue = make_issue(draft, config.issue_catalogue, config.field_rules)
        issues.setdefault(issue.issue_id, issue)
    return list(issues.values())


def find_owned_codes(field_rules: FieldRules) -> set[str]:
    """Return every code validation raises, including the condition groups' own codes."""
    group_codes = {group.issue_code for group in field_rules.condition_groups.values()}
    return set(codes.VALIDATION_CODES) | group_codes


def attach_issues(record: StoredRecord, issues: Sequence[Issue]) -> StoredRecord:
    """Return the record with its issue IDs (open and accepted) and its action needed."""
    action_needed = compute_action_needed(record, issues)
    # Excluded records were not checked, so their issue IDs stay as they were
    if record.exclusion is not None:
        return record.model_copy(update={"action_needed": action_needed})
    live = [
        issue
        for issue in issues
        if issue.record_id == record.record_id and issue.status != "resolved"
    ]
    fields = {key: attach_field_issues(stored, key, live) for key, stored in record.fields.items()}
    record_issue_ids = [issue.issue_id for issue in live if issue.field is None]
    return record.model_copy(
        update={"fields": fields, "issue_ids": record_issue_ids, "action_needed": action_needed}
    )


def attach_field_issues(stored: StoredField, key: str, live: Sequence[Issue]) -> StoredField:
    """Return the field with the IDs of its open and accepted issues."""
    issue_ids = [issue.issue_id for issue in live if issue.field == key]
    return stored.model_copy(update={"issue_ids": issue_ids})
