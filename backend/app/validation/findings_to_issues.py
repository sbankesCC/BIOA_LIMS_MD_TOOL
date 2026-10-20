"""Findings to issues: citation checks, verification verdicts and transform notes become issues.

Findings judge the extracted value, so once a person sets a field's value they no longer apply.
Transform notes describe the current value and always apply.
"""

import re
from collections.abc import Sequence

from pydantic import JsonValue

from app.config.field_rules import FieldRule
from app.contracts.record import StoredField, StoredRecord
from app.contracts.verification import (
    CitationCheck,
    FieldVerdict,
    RecordVerdict,
    VerificationOutput,
)
from app.ids import RECORD_PREFIX
from app.transform.notes import find_transform_notes
from app.transform.transform import USER_ORIGINS
from app.validation import codes
from app.validation.issues import IssueDraft

# Citation check results that need a person's look (CONTRACTS §2)
CITATION_CODES: dict[CitationCheck, str] = {
    "not_verified": codes.CITATION_NOT_VERIFIED,
    "not_checkable": codes.SCANNED_SOURCE,
}

# Verification agent verdicts on a field (CONTRACTS §3)
FIELD_VERDICT_CODES: dict[FieldVerdict, str] = {
    "contradicted": codes.CONTRADICTED_BY_SOURCE,
    "unsupported": codes.UNSUPPORTED_BY_SOURCE,
    "present_missed": codes.VALUE_PRESENT_MISSED,
}

# Verification agent verdicts on a whole record (CONTRACTS §3)
RECORD_VERDICT_CODES: dict[RecordVerdict, str] = {
    "not_a_consumable_type": codes.NOT_A_CONSUMABLE_TYPE,
    "duplicate_within_run": codes.POSSIBLE_DUPLICATE_IN_RUN,
    "should_be_split": codes.SHOULD_BE_SPLIT,
}

# Record IDs as the verification agent writes them in its notes
RECORD_ID_PATTERN = re.compile(rf"{RECORD_PREFIX}\d+")

# Shown for {other} when the agent's note names no other record of the run
OTHER_RECORD_FALLBACK = "another record in this run"

# Separator for lists of items in a message
ITEM_SEPARATOR = ", "


def is_set_by_person(stored: StoredField) -> bool:
    """Return True if a person set the field's value (edited or picked), not extraction."""
    return stored.output.origin in USER_ORIGINS


def find_field_finding_issues(
    record_id: str, rule: FieldRule, stored: StoredField
) -> list[IssueDraft]:
    """Return the issues from a field's citation check, agent verdict and transform notes."""
    value = stored.output.value
    drafts = find_transform_note_issues(record_id, rule, stored)
    verification = stored.verification
    if verification is None or is_set_by_person(stored):
        return drafts
    # The code citation check first, then the verification agent's verdict
    if verification.citation_check in CITATION_CODES:
        code = CITATION_CODES[verification.citation_check]
        drafts.append(IssueDraft(code=code, record_id=record_id, field=rule.key, value=value))
    if verification.verdict is not None:
        details: dict[str, JsonValue] = {"note": verification.note}
        drafts.append(
            IssueDraft(
                code=FIELD_VERDICT_CODES[verification.verdict],
                record_id=record_id,
                field=rule.key,
                value=value,
                details=details,
            )
        )
    return drafts


def find_transform_note_issues(
    record_id: str, rule: FieldRule, stored: StoredField
) -> list[IssueDraft]:
    """Return one issue per coded transform note (FORMAT_CORRECTED, DEFAULT_APPLIED, ...)."""
    drafts: list[IssueDraft] = []
    for note in find_transform_notes(stored.output.changes):
        # The note's own original and value fill the message; the current value keys the issue
        message_values = {
            name: text
            for name, text in (("original", note.original), ("value", note.value))
            if text is not None
        }
        drafts.append(
            IssueDraft(
                code=note.code,
                record_id=record_id,
                field=rule.key,
                value=stored.output.value,
                message_values=message_values,
            )
        )
    return drafts


def find_or_equivalent_issue(record: StoredRecord) -> list[IssueDraft]:
    """Return one OR_EQUIVALENT issue if any extracted value allows an equivalent product."""
    for stored in record.fields.values():
        extraction = stored.extraction
        if extraction is not None and extraction.allows_equivalent and not is_set_by_person(stored):
            return [IssueDraft(code=codes.OR_EQUIVALENT, record_id=record.record_id)]
    return []


def find_unreported_conflict_issues(
    record: StoredRecord, findings: VerificationOutput | None
) -> list[IssueDraft]:
    """Return an UNREPORTED_CONFLICT issue per conflict the agent found on this record."""
    if findings is None:
        return []
    drafts: list[IssueDraft] = []
    for conflict in findings.unreported_conflicts:
        stored = record.fields.get(conflict.field)
        if conflict.record_id != record.record_id or stored is None or is_set_by_person(stored):
            continue
        details: dict[str, JsonValue] = {"note": conflict.note, "sources": list(conflict.sources)}
        drafts.append(
            IssueDraft(
                code=codes.UNREPORTED_CONFLICT,
                record_id=record.record_id,
                field=conflict.field,
                value=stored.output.value,
                details=details,
            )
        )
    return drafts


def find_record_finding_issues(
    record: StoredRecord, run_record_ids: set[str], dropped_record_ids: set[str]
) -> list[IssueDraft]:
    """Return issues from the agent's record verdicts, and from a dropped re-extraction."""
    drafts: list[IssueDraft] = []
    for finding in record.verification.findings:
        message_values: dict[str, str] = {}
        if finding.verdict == "duplicate_within_run":
            message_values["other"] = find_other_records(finding.note, record, run_record_ids)
        drafts.append(
            IssueDraft(
                code=RECORD_VERDICT_CODES[finding.verdict],
                record_id=record.record_id,
                message_values=message_values,
                details={"note": finding.note},
            )
        )
    if record.record_id in dropped_record_ids:
        drafts.append(
            IssueDraft(code=codes.RECORD_DROPPED_ON_REEXTRACTION, record_id=record.record_id)
        )
    return drafts


def find_other_records(note: str, record: StoredRecord, run_record_ids: set[str]) -> str:
    """Return the other run records the agent's note names, for the {other} placeholder."""
    named = [
        record_id
        for record_id in dict.fromkeys(RECORD_ID_PATTERN.findall(note))
        if record_id in run_record_ids and record_id != record.record_id
    ]
    return ITEM_SEPARATOR.join(named) if named else OTHER_RECORD_FALLBACK


def find_run_finding_issues(findings: VerificationOutput | None) -> list[IssueDraft]:
    """Return run issues for missed candidates and challenged excluded items."""
    if findings is None:
        return []
    drafts: list[IssueDraft] = []
    missed = [candidate.name_as_written for candidate in findings.missed_candidates]
    challenged = [challenge.item for challenge in findings.excluded_item_challenges]
    # One run issue per kind; the list of items keys it, so a new list is a new issue
    for code, items in (
        (codes.MISSED_CANDIDATES_UNRESOLVED, missed),
        (codes.EXCLUDED_ITEM_CHALLENGED, challenged),
    ):
        if items:
            drafts.append(make_items_issue(code, items))
    return drafts


def make_items_issue(code: str, items: Sequence[str]) -> IssueDraft:
    """Return a run issue draft that lists items in its message."""
    text = ITEM_SEPARATOR.join(items)
    return IssueDraft(
        code=code, value=text, message_values={"items": text}, details={"items": list(items)}
    )
