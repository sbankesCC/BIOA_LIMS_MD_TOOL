"""Shared helpers for validation tests: synthetic records, a fake judge, and a validation run.

Field keys and lookup values are read from the client config, never written here.
"""

from collections.abc import Callable, Sequence

from app.config.bundle import ConfigBundle
from app.config.field_rules import FieldRule, FieldRules
from app.config.lookup_lists import LookupLists
from app.contracts.extraction import ExtractedField
from app.contracts.issue import Issue
from app.contracts.judge import JudgeOutput, JudgeVerdict, Judgment
from app.contracts.record import (
    FieldOutput,
    FieldVerification,
    Origin,
    RecordExtraction,
    StoredField,
    StoredRecord,
)
from app.contracts.reference import ReferenceData, ReferenceType
from app.transform.lookup_matching import BOOLEAN_VALUES
from app.validation.duplicates import find_name_rule
from app.validation.judge_cache import InMemoryJudgeCache, JudgeCache, JudgeRequest, JudgeRunner
from app.validation.service import (
    ProcessingFindings,
    ValidationResult,
    make_validation_config,
    validate_run,
)

SYNTHETIC_TEXT = "synthetic"
JUDGE_PROMPT_VERSION = "test-prompt-1"
EMPTY_REFERENCE = ReferenceData(version="ref-synthetic-1", types=[])


class FakeJudge:
    """A duplicate judge that gives one verdict to every candidate and counts its calls."""

    def __init__(self, verdict: JudgeVerdict = "different") -> None:
        """Set the verdict every candidate gets."""
        self.verdict: JudgeVerdict = verdict
        self.requests: list[JudgeRequest] = []

    def judge(self, request: JudgeRequest) -> JudgeOutput:
        """Record the request and judge every candidate with the set verdict."""
        self.requests.append(request)
        return JudgeOutput(
            judgments=[
                Judgment(candidate_id=c.candidate_id, verdict=self.verdict, reason="synthetic")
                for c in request.candidates
            ]
        )


def find_rule(field_rules: FieldRules, is_wanted: Callable[[FieldRule], bool]) -> FieldRule:
    """Return the first extracted field rule that `is_wanted` accepts."""
    return next(rule for rule in field_rules.extracted_fields() if is_wanted(rule))


def valid_value(rule: FieldRule, lookup_lists: LookupLists) -> str:
    """Return a value that passes the field's checks (as far as the config allows)."""
    if rule.lookup_sheet is not None:
        values = lookup_lists.sheets[rule.lookup_sheet]
        limit = rule.max_length or len(max(values, key=len))
        return next((value for value in values if len(value) <= limit), values[0])
    if rule.type == "boolean":
        return BOOLEAN_VALUES[0]
    if rule.type in ("decimal", "integer"):
        return "1"
    return SYNTHETIC_TEXT[: rule.max_length]


def make_record(
    bundle: ConfigBundle, record_id: str = "rec_0001", name: str = "Syn A"
) -> StoredRecord:
    """Build a synthetic record with a valid found value in every extracted field."""
    fields: dict[str, StoredField] = {}
    name_key = find_name_rule(bundle.field_rules).key
    for rule in bundle.field_rules.fields:
        if rule.role != "extracted":
            fields[rule.key] = StoredField(output=FieldOutput(origin=rule.role))
            continue
        value = name if rule.key == name_key else valid_value(rule, bundle.lookup_lists)
        fields[rule.key] = StoredField(
            extraction=ExtractedField(status="found", value=value),
            verification=FieldVerification(citation_check="verified"),
            output=FieldOutput(value=value, origin="extracted"),
        )
    return StoredRecord(
        record_id=record_id,
        found_in=["doc01-c001"],
        extraction=RecordExtraction(record_ref="R1", record_summary="synthetic record"),
        fields=fields,
    )


def set_output(
    record: StoredRecord,
    key: str,
    value: str | None,
    origin: Origin = "extracted",
    changes: Sequence[str] = (),
) -> StoredRecord:
    """Return the record with one field's output replaced."""
    output = FieldOutput(value=value, origin=origin, changes=list(changes))
    return update_field(record, key, record.fields[key].model_copy(update={"output": output}))


def update_field(record: StoredRecord, key: str, stored: StoredField) -> StoredRecord:
    """Return the record with one field replaced."""
    return record.model_copy(update={"fields": {**record.fields, key: stored}})


def run_validation(
    bundle: ConfigBundle,
    records: Sequence[StoredRecord],
    reference: ReferenceData | None = EMPTY_REFERENCE,
    judge: FakeJudge | None = None,
    cache: JudgeCache | None = None,
    call_limit: int | None = None,
    findings: ProcessingFindings | None = None,
    previous_issues: Sequence[Issue] = (),
) -> ValidationResult:
    """Run the validation service with test defaults (empty reference data, no call limit)."""
    runner = JudgeRunner(
        judge or FakeJudge(), cache or InMemoryJudgeCache(), JUDGE_PROMPT_VERSION, call_limit
    )
    return validate_run(
        records,
        make_validation_config(bundle),
        runner,
        reference,
        findings,
        previous_issues,
    )


def issues_with_code(result: ValidationResult, code: str) -> list[Issue]:
    """Return the open issues with one code."""
    return [issue for issue in result.issues if issue.code == code and issue.status == "open"]


def make_reference(*names: str, active_flag: str | None = None) -> ReferenceData:
    """Return synthetic reference data with one existing type per name."""
    types = [
        ReferenceType(
            candidate_id=f"ref_{number:04d}",
            name=name,
            version="1",
            active_flag=active_flag,
        )
        for number, name in enumerate(names, start=1)
    ]
    return ReferenceData(version="ref-synthetic-1", types=types)
