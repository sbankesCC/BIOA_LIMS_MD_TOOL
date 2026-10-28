"""Eval scoring: compares one run's records with a case's expected extraction.

Scores: records (recall and precision), field values, field status, citations (expected document
and page or section), seeded errors caught and correct values wrongly flagged. Records are
matched by normalized name. A field the case does not label is not counted, nor is an unscored one.
"""

from collections.abc import Iterable, Sequence

from pydantic import BaseModel, ValidationError, computed_field

from app.contracts.eval_case import (
    ExpectedExtraction,
    ExpectedField,
    ExpectedRecord,
    ExpectedSource,
    SeededError,
)
from app.contracts.extraction import ExtractedField, ExtractedValue
from app.contracts.verification import FieldFinding, VerificationOutput
from app.transform.lookup_matching import normalize_for_match


class Score(BaseModel):
    """A count of correct items out of a total; the rate is empty when nothing was counted."""

    correct: int = 0
    total: int = 0

    @computed_field
    @property
    def rate(self) -> float | None:
        """Return correct / total, or None when the total is zero."""
        return self.correct / self.total if self.total else None

    def add(self, other: "Score") -> "Score":
        """Return the sum of two scores."""
        return Score(correct=self.correct + other.correct, total=self.total + other.total)


class ActualSource(BaseModel):
    """Where a run's record was found: document file name, page, section and sheet."""

    document: str
    page: int | None = None
    section: str | None = None
    sheet: str | None = None


class ActualRecord(BaseModel):
    """A run's record as scoring sees it: name, sources, extraction and output per field."""

    record_id: str
    name: str | None
    sources: list[ActualSource] = []
    fields: dict[str, ExtractedField | None] = {}
    output_values: dict[str, str | None] = {}


class RecordMatch(BaseModel):
    """Expected and actual records paired by index, and the indexes left over on each side."""

    pairs: list[tuple[int, int]]
    unmatched_expected: list[int]
    unmatched_actual: list[int]


class FieldResult(BaseModel):
    """Whether one labeled field's value and status are right."""

    field: str
    is_value_correct: bool
    is_status_correct: bool


class FieldTally(BaseModel):
    """Value and status scores of one field, summed over records."""

    values: Score = Score()
    status: Score = Score()


class RecordResult(BaseModel):
    """Scores of one expected record (record ID is None when no record matched it)."""

    expected_name: str
    record_id: str | None
    field_values: Score
    field_status: Score
    citations: Score
    wrong_fields: list[str]


class SeededResult(BaseModel):
    """One seeded error: whether it was planted, the verdicts given, and whether it was caught."""

    record: str
    field: str
    expected_verdict: str
    is_planted: bool
    verdicts_given: list[str]
    is_caught: bool


class RunScores(BaseModel):
    """Every score of one run."""

    record_recall: Score
    record_precision: Score
    field_values: Score
    field_status: Score
    citations: Score
    seeded_errors_caught: Score
    correct_values_flagged: Score


class RunScoring(BaseModel):
    """One run's scores with the details behind them."""

    scores: RunScores
    records: list[RecordResult]
    by_field: dict[str, FieldTally]
    unmatched_expected: list[str]
    unmatched_actual: list[str]
    seeded_errors: list[SeededResult]


def select_scored_fields(extracted_keys: Iterable[str], unscored_keys: set[str]) -> list[str]:
    """Return the extracted field keys that are scored, in field order."""
    return [key for key in extracted_keys if key not in unscored_keys]


def normalize_text(text: str) -> str:
    """Return the text with whitespace runs collapsed to one space and the ends trimmed."""
    return " ".join(text.split())


def match_records(
    expected: Sequence[ExpectedRecord], actual: Sequence[ActualRecord]
) -> RecordMatch:
    """Pair records by normalized name (case, spaces, "°" ignored); each is used once."""
    pairs: list[tuple[int, int]] = []
    used_actual: set[int] = set()
    for expected_index, record in enumerate(expected):
        wanted = normalize_for_match(record.name)
        for actual_index, candidate in enumerate(actual):
            if actual_index in used_actual or candidate.name is None:
                continue
            if normalize_for_match(candidate.name) == wanted:
                pairs.append((expected_index, actual_index))
                used_actual.add(actual_index)
                break
    matched_expected = {expected_index for expected_index, _ in pairs}
    return RecordMatch(
        pairs=pairs,
        unmatched_expected=[i for i in range(len(expected)) if i not in matched_expected],
        unmatched_actual=[i for i in range(len(actual)) if i not in used_actual],
    )


def values_equal(expected: ExtractedValue | None, actual: ExtractedValue | None) -> bool:
    """Compare two values with whitespace collapsed; lists compare as sets of entries."""
    if expected is None or actual is None:
        return expected is None and actual is None
    if isinstance(expected, list) or isinstance(actual, list):
        expected_list = expected if isinstance(expected, list) else [expected]
        actual_list = actual if isinstance(actual, list) else [actual]
        return {normalize_text(item) for item in expected_list} == {
            normalize_text(item) for item in actual_list
        }
    return normalize_text(expected) == normalize_text(actual)


def alternatives_equal(expected: Sequence[ExtractedValue], actual: ExtractedField) -> bool:
    """Return True when a conflict gives the expected alternatives (in any order)."""
    actual_values = [alternative.value for alternative in actual.alternatives]
    if len(actual_values) != len(expected):
        return False
    remaining = list(actual_values)
    # Each expected alternative must use up one equal actual alternative
    for value in expected:
        match = next((item for item in remaining if values_equal(value, item)), None)
        if match is None:
            return False
        remaining.remove(match)
    return True


def is_value_correct(
    expected: ExpectedField, actual: ExtractedField, output_value: str | None
) -> bool:
    """Check a value as written or as exported (labels may use either); conflicts by options."""
    if expected.status != actual.status:
        return False
    if expected.status == "conflicting":
        return alternatives_equal(expected.alternatives, actual)
    if expected.status == "not_found":
        return True
    return values_equal(expected.value, actual.value) or values_equal(expected.value, output_value)


def score_field(
    key: str, expected: ExpectedField, actual: ExtractedField | None, output_value: str | None
) -> FieldResult:
    """Score one labeled field; a field the run did not extract is wrong on both counts."""
    if actual is None:
        return FieldResult(field=key, is_value_correct=False, is_status_correct=False)
    return FieldResult(
        field=key,
        is_value_correct=is_value_correct(expected, actual, output_value),
        is_status_correct=expected.status == actual.status,
    )


def score_record_fields(
    expected: ExpectedRecord, actual: ActualRecord | None, scored_fields: Sequence[str]
) -> list[FieldResult]:
    """Score every labeled, scored field of a record; unlabeled fields are not counted."""
    results: list[FieldResult] = []
    for key in scored_fields:
        label = expected.fields.get(key)
        if label is None:
            continue
        actual_field = actual.fields.get(key) if actual is not None else None
        output_value = actual.output_values.get(key) if actual is not None else None
        results.append(score_field(key, label, actual_field, output_value))
    return results


def is_source_found(expected: ExpectedSource, sources: Sequence[ActualSource]) -> bool:
    """Return True when a source is in the expected document, page and section (or sheet)."""
    for source in sources:
        if source.document.casefold() != expected.document.casefold():
            continue
        if expected.page is not None and source.page != expected.page:
            continue
        if expected.section is not None and not is_section_match(expected.section, source):
            continue
        return True
    return False


def is_section_match(section: str, source: ActualSource) -> bool:
    """Match a labeled section to a heading path (contained in it) or a sheet name (equal)."""
    wanted = normalize_text(section).casefold()
    heading_path = normalize_text(source.section or "").casefold()
    sheet = normalize_text(source.sheet or "").casefold()
    return wanted in heading_path or wanted == sheet


def score_citations(expected: ExpectedRecord, actual: ActualRecord | None) -> Score:
    """Count the expected sources the record's "found in" chunks point to."""
    sources = actual.sources if actual is not None else []
    found = sum(1 for source in expected.found_in if is_source_found(source, sources))
    return Score(correct=found, total=len(expected.found_in))


def count_results(results: Sequence[FieldResult]) -> tuple[Score, Score]:
    """Return (value score, status score) of a list of field results."""
    values = Score(correct=sum(result.is_value_correct for result in results), total=len(results))
    status = Score(correct=sum(result.is_status_correct for result in results), total=len(results))
    return values, status


def collect_field_findings(verification_texts: Iterable[str]) -> list[FieldFinding]:
    """Return the field findings of every verification reply; unreadable replies are skipped."""
    findings: list[FieldFinding] = []
    for text in verification_texts:
        try:
            output = VerificationOutput.model_validate_json(text)
        except ValidationError:
            continue
        findings.extend(output.field_findings)
    return findings


def score_seeded_errors(
    seeded: Sequence[SeededError],
    planted: Sequence[SeededError],
    findings: Sequence[FieldFinding],
    names_by_id: dict[str, str],
) -> list[SeededResult]:
    """Check each seeded error: caught when planted and given the expected verdict."""
    results: list[SeededResult] = []
    for error in seeded:
        wanted = normalize_for_match(error.record)
        verdicts = [
            finding.verdict
            for finding in findings
            if finding.field == error.field
            and normalize_for_match(names_by_id.get(finding.record_id, "")) == wanted
        ]
        is_planted = error in planted
        results.append(
            SeededResult(
                record=error.record,
                field=error.field,
                expected_verdict=error.expected_verdict,
                is_planted=is_planted,
                verdicts_given=verdicts,
                is_caught=is_planted and error.expected_verdict in verdicts,
            )
        )
    return results


def count_flagged_correct_values(
    correct_fields: set[tuple[str, str]],
    seeded_fields: set[tuple[str, str]],
    findings: Sequence[FieldFinding],
) -> Score:
    """Count correct (record ID, field) values that a verification finding flagged.

    Seeded fields are left out: flagging a planted value is right.
    """
    checked = correct_fields - seeded_fields
    flagged = {(finding.record_id, finding.field) for finding in findings} & checked
    return Score(correct=len(flagged), total=len(checked))


def score_run(
    expected: ExpectedExtraction,
    actual: Sequence[ActualRecord],
    scored_fields: Sequence[str],
    seeded: Sequence[SeededError],
    planted: Sequence[SeededError],
    findings: Sequence[FieldFinding],
) -> RunScoring:
    """Score one run against the expected extraction."""
    match = match_records(expected.records, actual)
    paired = dict(match.pairs)
    record_results: list[RecordResult] = []
    by_field: dict[str, FieldTally] = {}
    correct_fields: set[tuple[str, str]] = set()
    # Score each expected record against its matched record (or none)
    for index, record in enumerate(expected.records):
        actual_record = actual[paired[index]] if index in paired else None
        results = score_record_fields(record, actual_record, scored_fields)
        record_results.append(make_record_result(record, actual_record, results))
        add_to_field_tallies(by_field, results)
        if actual_record is not None:
            correct_fields |= {
                (actual_record.record_id, result.field)
                for result in results
                if result.is_value_correct
            }
    names_by_id = {record.record_id: record.name or "" for record in actual}
    seeded_results = score_seeded_errors(seeded, planted, findings, names_by_id)
    seeded_fields = find_seeded_fields(seeded, actual)
    scores = make_run_scores(
        match, record_results, seeded_results, correct_fields, seeded_fields, findings
    )
    return RunScoring(
        scores=scores,
        records=record_results,
        by_field=by_field,
        unmatched_expected=[expected.records[i].name for i in match.unmatched_expected],
        unmatched_actual=[actual[i].record_id for i in match.unmatched_actual],
        seeded_errors=seeded_results,
    )


def make_record_result(
    expected: ExpectedRecord, actual: ActualRecord | None, results: Sequence[FieldResult]
) -> RecordResult:
    """Build one expected record's result from its field results and citations."""
    values, status = count_results(results)
    return RecordResult(
        expected_name=expected.name,
        record_id=actual.record_id if actual is not None else None,
        field_values=values,
        field_status=status,
        citations=score_citations(expected, actual),
        wrong_fields=[result.field for result in results if not result.is_value_correct],
    )


def add_to_field_tallies(by_field: dict[str, FieldTally], results: Sequence[FieldResult]) -> None:
    """Add field results to the per-field tallies."""
    for result in results:
        tally = by_field.setdefault(result.field, FieldTally())
        values, status = count_results([result])
        by_field[result.field] = FieldTally(
            values=tally.values.add(values), status=tally.status.add(status)
        )


def find_seeded_fields(
    seeded: Sequence[SeededError], actual: Sequence[ActualRecord]
) -> set[tuple[str, str]]:
    """Return the (record ID, field) pairs of the run's records that carry a seeded error."""
    wanted = {(normalize_for_match(error.record), error.field) for error in seeded}
    return {
        (record.record_id, field)
        for record in actual
        for name, field in wanted
        if record.name is not None and normalize_for_match(record.name) == name
    }


def make_run_scores(
    match: RecordMatch,
    records: Sequence[RecordResult],
    seeded: Sequence[SeededResult],
    correct_fields: set[tuple[str, str]],
    seeded_fields: set[tuple[str, str]],
    findings: Sequence[FieldFinding],
) -> RunScores:
    """Sum the record, field, citation and seeded error scores of one run."""
    matched = len(match.pairs)
    planted = [result for result in seeded if result.is_planted]
    return RunScores(
        record_recall=Score(correct=matched, total=matched + len(match.unmatched_expected)),
        record_precision=Score(correct=matched, total=matched + len(match.unmatched_actual)),
        field_values=sum_scores(record.field_values for record in records),
        field_status=sum_scores(record.field_status for record in records),
        citations=sum_scores(record.citations for record in records),
        seeded_errors_caught=Score(
            correct=sum(result.is_caught for result in planted), total=len(planted)
        ),
        correct_values_flagged=count_flagged_correct_values(
            correct_fields, seeded_fields, findings
        ),
    )


def sum_scores(scores: Iterable[Score]) -> Score:
    """Return the sum of several scores."""
    total = Score()
    for score in scores:
        total = total.add(score)
    return total
