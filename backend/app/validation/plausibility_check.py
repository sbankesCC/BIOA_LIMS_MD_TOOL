"""Plausibility review (8.6): values that do not fit together become yellow PLAUSIBILITY_CHECK.

Only values that passed the field checks (8.1) are shown to the model. Each kept finding is
raised on the first field it lists, with the check ID and reason. A skipped review (blank model,
call limit, failed call) adds the run-level PLAUSIBILITY_SKIPPED. Never changes a value.
"""

from collections.abc import Sequence
from typing import Protocol

from app.agents.plausibility import PlausibilityResult
from app.config.business_rules import BusinessRules
from app.config.lookup_lists import LookupLists
from app.contracts.plausibility import PlausibilityFinding, PlausibilityRecord
from app.contracts.record import StoredRecord
from app.validation import codes
from app.validation.field_checks import check_field
from app.validation.issues import IssueDraft


class PlausibilityReviewer(Protocol):
    """Reviews records for implausible combinations of values (the LLM agent, or a fake)."""

    def review(self, records: list[PlausibilityRecord]) -> PlausibilityResult:
        """Return the kept findings, or a skipped result."""
        ...


def find_plausibility_drafts(
    records: Sequence[StoredRecord],
    business_rules: BusinessRules,
    lookup_lists: LookupLists,
    reviewer: PlausibilityReviewer,
) -> list[IssueDraft]:
    """Review the included records and return an issue per finding (and a run issue if skipped)."""
    to_review = [build_review_record(r, business_rules, lookup_lists) for r in records]
    result = reviewer.review(to_review)
    by_id = {record.record_id: record for record in records}
    drafts: list[IssueDraft] = []
    for finding in result.findings:
        draft = make_finding_draft(finding, by_id.get(finding.record_id), business_rules)
        if draft is not None:
            drafts.append(draft)
    if result.is_skipped:
        drafts.append(IssueDraft(code=codes.PLAUSIBILITY_SKIPPED))
    return drafts


def build_review_record(
    record: StoredRecord, business_rules: BusinessRules, lookup_lists: LookupLists
) -> PlausibilityRecord:
    """Return the record as the model sees it: final values that passed the field checks."""
    name_key = business_rules.record_name_field().key
    values: dict[str, str] = {}
    for rule in business_rules.fields:
        stored = record.fields.get(rule.key)
        if stored is None or not stored.output.value:
            continue
        # Extracted fields must pass 8.1; derived fields are shown as final values
        if rule.is_extracted and check_field(record.record_id, rule, stored, lookup_lists):
            continue
        values[rule.key] = stored.output.value
    return PlausibilityRecord(
        record_id=record.record_id,
        name=values.get(name_key),
        values=values,
        context=read_found_context(record),
    )


def read_found_context(record: StoredRecord) -> dict[str, str]:
    """Return the context attribute values that were found, by key."""
    found: dict[str, str] = {}
    for key, attribute in record.context.items():
        extraction = attribute.extraction
        if extraction is not None and extraction.status == "found" and extraction.value:
            value = extraction.value
            found[key] = value if isinstance(value, str) else ", ".join(value)
    return found


def make_finding_draft(
    finding: PlausibilityFinding, record: StoredRecord | None, business_rules: BusinessRules
) -> IssueDraft | None:
    """Return the issue for a finding on its first known field, or None if it names none."""
    if record is None:
        return None
    known = {rule.key for rule in business_rules.fields}
    keys = [key for key in finding.fields if key in known]
    if not keys:
        return None
    stored = record.fields.get(keys[0])
    return IssueDraft(
        code=codes.PLAUSIBILITY_CHECK,
        record_id=record.record_id,
        field=keys[0],
        # The check ID is part of the key, so two checks on one value stay two issues
        value=f"{finding.check_id}: {stored.output.value if stored is not None else ''}",
        message_values={"check_id": finding.check_id, "reason": finding.reason},
        details={"check_id": finding.check_id},
    )
