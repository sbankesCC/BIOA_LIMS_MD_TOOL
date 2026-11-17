"""Shared helpers for validation tests: synthetic records, a fake judge, and a validation run.

Field keys and lookup values are read from the client config, never written here.
"""

from collections.abc import Callable, Sequence

from app.assembly.assemble import assemble_record
from app.config.bundle import ConfigBundle
from app.config.business_rules import BusinessRules, FieldDefinition
from app.config.lookup_lists import LookupLists
from app.contracts.extraction import ExtractedField
from app.contracts.issue import Issue
from app.contracts.judge import JudgeOutput, JudgeVerdict, Judgment
from app.contracts.record import (
    FieldNormalization,
    FieldOutput,
    FieldVerification,
    Origin,
    RecordExtraction,
    StoredContextAttribute,
    StoredField,
    StoredRecord,
    find_initial_origin,
)
from app.contracts.reference import ReferenceData, ReferenceType
from app.normalization.lookup_matching import BOOLEAN_VALUES
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


def find_rule(
    business_rules: BusinessRules, is_wanted: Callable[[FieldDefinition], bool]
) -> FieldDefinition:
    """Return the first extracted field definition that `is_wanted` accepts."""
    return next(rule for rule in business_rules.extracted_fields() if is_wanted(rule))


def valid_value(rule: FieldDefinition, lookup_lists: LookupLists) -> str:
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
    name_key = find_name_rule(bundle.business_rules).key
    for rule in bundle.business_rules.fields:
        if not rule.is_extracted:
            fields[rule.key] = StoredField(output=FieldOutput(origin=find_initial_origin(rule)))
            continue
        value = name if rule.key == name_key else valid_value(rule, bundle.lookup_lists)
        fields[rule.key] = StoredField(
            extraction=ExtractedField(status="found", value=value),
            verification=FieldVerification(citation_check="verified"),
            normalization=FieldNormalization(value=value),
            output=FieldOutput(value=value, origin="extracted"),
        )
    record = StoredRecord(
        record_id=record_id,
        found_in=["doc01-c001"],
        extraction=RecordExtraction(record_ref="R1", record_summary="synthetic record"),
        context=make_context(bundle),
        fields=fields,
    )
    # Derived fields get their values from Assembly, as in a processed record
    return assemble_record(record, bundle.business_rules)


def make_context(bundle: ConfigBundle) -> dict[str, StoredContextAttribute]:
    """Return every context attribute found with a synthetic value, so derivations can run."""
    found = ExtractedField(status="found", value=SYNTHETIC_TEXT)
    return {
        attribute.key: StoredContextAttribute(
            extraction=found, verification=FieldVerification(citation_check="verified")
        )
        for attribute in bundle.business_rules.context_fields()
    }


def make_red_record(
    bundle: ConfigBundle, record_id: str = "rec_0001", name: str = "Syn A"
) -> StoredRecord:
    """Build a synthetic record whose first free-text field with a limit is too long (an error)."""
    rule = find_rule(
        bundle.business_rules,
        lambda rule: (
            rule.max_length is not None and rule.lookup_sheet is None and not rule.is_record_name
        ),
    )
    record = make_record(bundle, record_id, name)
    return set_output(record, rule.key, "x" * ((rule.max_length or 0) + 1))


def set_output(
    record: StoredRecord,
    key: str,
    value: str | None,
    origin: Origin = "extracted",
    changes: Sequence[str] = (),
) -> StoredRecord:
    """Return the record with one field's output replaced.

    An extracted field's normalization follows its output, so Assembly (which rebuilds the
    output from it) gives the same value.
    """
    output = FieldOutput(value=value, origin=origin, changes=list(changes))
    stored = record.fields[key]
    update: dict[str, object] = {"output": output}
    if stored.normalization is not None and origin == "extracted":
        update["normalization"] = FieldNormalization(value=value)
    return update_field(record, key, stored.model_copy(update=update))


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
    prompt_version: str = JUDGE_PROMPT_VERSION,
) -> ValidationResult:
    """Run the validation service with test defaults (empty reference data, no call limit)."""
    runner = JudgeRunner(
        judge or FakeJudge(), cache or InMemoryJudgeCache(), prompt_version, call_limit
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
