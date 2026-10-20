"""Duplicate checks: the name must be unique in the run and new to LabVantage.

Against the reference data: an exact name match is EXISTS_IN_LABVANTAGE; a normalized match
(case, spaces, degree sign) is POSSIBLE_DUPLICATE; otherwise similar names are shortlisted and
the duplicate judge decides. The record name field and the fields the judge sees are flagged
in the field rules (`is_record_name`, `sent_to_duplicate_judge`).
"""

from collections import defaultdict
from collections.abc import Sequence
from difflib import SequenceMatcher

from pydantic import BaseModel, JsonValue

from app.config.field_rules import FieldRule, FieldRules
from app.config.reference_mapping import ReferenceRules
from app.contracts.issue import DuplicateCandidate
from app.contracts.judge import JudgeOutput
from app.contracts.record import StoredRecord
from app.contracts.reference import ReferenceData, ReferenceType
from app.transform.lookup_matching import BOOLEAN_VALUES, normalize_for_match
from app.validation import codes
from app.validation.issues import IssueDraft
from app.validation.judge_cache import JudgeRequest, JudgeRunner

# How alike two normalized names must be (0 to 1, difflib ratio) to go on the judge's shortlist
SIMILARITY_THRESHOLD = 0.6

# Judge verdicts that make a record a possible duplicate (CONTRACTS §3a)
DUPLICATE_VERDICTS = ("same", "unsure")

# The active flag value of an inactive existing type (LabVantage Y/N flag)
INACTIVE_FLAG = BOOLEAN_VALUES[1]


class ReferenceCheck(BaseModel):
    """The reference data result for one record: its issues and whether the judge was skipped."""

    drafts: list[IssueDraft] = []
    is_judge_skipped: bool = False


def find_name_rule(field_rules: FieldRules) -> FieldRule:
    """Return the field that names a record: the one flagged `is_record_name` in the config."""
    return field_rules.record_name_field()


def read_name(record: StoredRecord, name_rule: FieldRule) -> str | None:
    """Return the record's current name, or None if it is empty."""
    stored = record.fields.get(name_rule.key)
    if stored is None or not stored.output.value:
        return None
    return stored.output.value


def find_run_duplicates(records: Sequence[StoredRecord], name_rule: FieldRule) -> list[IssueDraft]:
    """Return a DUPLICATE_IN_RUN issue on each record whose name another record also has."""
    records_by_name: dict[str, list[str]] = defaultdict(list)
    for record in records:
        name = read_name(record, name_rule)
        if name is not None:
            records_by_name[name].append(record.record_id)
    drafts: list[IssueDraft] = []
    for name, record_ids in records_by_name.items():
        if len(record_ids) < 2:
            continue
        # Each record lists the others with the same name
        for record_id in record_ids:
            others: list[JsonValue] = [other for other in record_ids if other != record_id]
            drafts.append(
                IssueDraft(
                    code=codes.DUPLICATE_IN_RUN,
                    record_id=record_id,
                    field=name_rule.key,
                    value=name,
                    details={"records": others},
                )
            )
    return drafts


def find_identifying_values(record: StoredRecord, field_rules: FieldRules) -> dict[str, str | None]:
    """Return the values of the fields flagged `sent_to_duplicate_judge`: what the judge sees.

    The judge cache key is built from exactly these values. A field missing from the record is None.
    """
    values: dict[str, str | None] = {}
    for rule in field_rules.duplicate_judge_fields():
        stored = record.fields.get(rule.key)
        values[rule.key] = stored.output.value if stored is not None else None
    return values


def is_exact_match(name: str, existing: ReferenceType, rules: ReferenceRules) -> bool:
    """Return True if an existing type has exactly this name and counts as taken."""
    if existing.name != name:
        return False
    # By default the name is taken even when the existing type is inactive
    return rules.exact_match_ignores_active_flag or existing.active_flag != INACTIVE_FLAG


def build_shortlist(
    name: str, types: Sequence[ReferenceType], shortlist_size: int
) -> list[ReferenceType]:
    """Return up to `shortlist_size` existing types with similar names, most similar first."""
    normalized = normalize_for_match(name)
    scored: list[tuple[float, ReferenceType]] = []
    for existing in types:
        ratio = SequenceMatcher(None, normalized, normalize_for_match(existing.name)).ratio()
        if ratio >= SIMILARITY_THRESHOLD:
            scored.append((ratio, existing))
    # Ties are broken by name so the shortlist is the same on every run
    scored.sort(key=lambda pair: (-pair[0], pair[1].name))
    return [existing for _, existing in scored[:shortlist_size]]


def make_name_issue(
    code: str, record_id: str, name_rule: FieldRule, name: str, candidates: list[JsonValue]
) -> IssueDraft:
    """Return an issue on the record's name field listing the matching existing types."""
    return IssueDraft(
        code=code,
        record_id=record_id,
        field=name_rule.key,
        value=name,
        details={"candidates": candidates},
    )


def describe_candidate(existing: ReferenceType, match: str, reason: str | None) -> JsonValue:
    """Return one matching existing type as issue details: its ID, name and why it matched.

    Its description, class and active flag are copied from the reference data (None when absent)
    so the review can compare them; details never key the issue, so its ID does not change.
    """
    candidate = DuplicateCandidate(
        candidate_id=existing.candidate_id,
        name=existing.name,
        match=match,
        reason=reason,
        description=existing.description,
        consumable_class=existing.consumable_class,
        active_flag=existing.active_flag,
    )
    return candidate.model_dump(mode="json")


def check_reference(
    record: StoredRecord,
    field_rules: FieldRules,
    reference: ReferenceData,
    rules: ReferenceRules,
    runner: JudgeRunner,
) -> ReferenceCheck:
    """Check one record's name against the existing Consumable Types."""
    name_rule = find_name_rule(field_rules)
    name = read_name(record, name_rule)
    if name is None:
        return ReferenceCheck()
    record_id = record.record_id
    # An exact match is a hard stop: LabVantage will not accept the name again
    exact = [existing for existing in reference.types if is_exact_match(name, existing, rules)]
    if exact:
        candidates = [describe_candidate(existing, "exact", None) for existing in exact]
        draft = make_name_issue(codes.EXISTS_IN_LABVANTAGE, record_id, name_rule, name, candidates)
        return ReferenceCheck(drafts=[draft])
    # The same name apart from case, spaces or degree signs needs no judge
    normalized = normalize_for_match(name)
    close = [t for t in reference.types if normalize_for_match(t.name) == normalized]
    if close:
        candidates = [describe_candidate(existing, "normalized", None) for existing in close]
        draft = make_name_issue(codes.POSSIBLE_DUPLICATE, record_id, name_rule, name, candidates)
        return ReferenceCheck(drafts=[draft])
    return judge_shortlist(record, field_rules, reference, rules, runner)


def judge_shortlist(
    record: StoredRecord,
    field_rules: FieldRules,
    reference: ReferenceData,
    rules: ReferenceRules,
    runner: JudgeRunner,
) -> ReferenceCheck:
    """Ask the judge about similar existing types; same or unsure gives POSSIBLE_DUPLICATE."""
    name_rule = find_name_rule(field_rules)
    name = read_name(record, name_rule) or ""
    shortlist = build_shortlist(name, reference.types, rules.shortlist_size)
    if not shortlist:
        return ReferenceCheck()
    request = JudgeRequest(
        record_id=record.record_id,
        values=find_identifying_values(record, field_rules),
        candidates=shortlist,
    )
    output = runner.judge_record(request, reference.version)
    if output is None:
        return ReferenceCheck(is_judge_skipped=True)
    candidates = find_duplicate_candidates(output, shortlist)
    if not candidates:
        return ReferenceCheck()
    draft = make_name_issue(codes.POSSIBLE_DUPLICATE, record.record_id, name_rule, name, candidates)
    return ReferenceCheck(drafts=[draft])


def find_duplicate_candidates(
    output: JudgeOutput, shortlist: Sequence[ReferenceType]
) -> list[JsonValue]:
    """Return the shortlisted types the judge called same or unsure, with its reasons."""
    by_id = {existing.candidate_id: existing for existing in shortlist}
    candidates: list[JsonValue] = []
    for judgment in output.judgments:
        # Judgments on IDs that were not shortlisted are ignored
        existing = by_id.get(judgment.candidate_id)
        if existing is not None and judgment.verdict in DUPLICATE_VERDICTS:
            candidates.append(describe_candidate(existing, judgment.verdict, judgment.reason))
    return candidates
