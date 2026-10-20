"""Eval report tests: score spreads, tag and field summaries, and the JSON and CSV files' shape.

Run outcomes and scores are built by hand from synthetic values; no graph runs here.
"""

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from app.config.bundle import ConfigBundle
from app.contracts.eval_case import EvalCaseInfo, ExpectedExtraction
from app.evals.case_loader import EvalCase
from app.evals.report import (
    CSV_COLUMNS,
    SCORE_NAMES,
    CaseResult,
    SuiteReport,
    make_case_result,
    make_run_result,
    summarize_fields,
    summarize_tags,
    write_report,
)
from app.evals.runner import CaseOutcome, RunOutcome
from app.evals.scoring import FieldTally, RunScores, RunScoring, Score

STARTED = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


def make_scores(field_correct: int) -> RunScores:
    """Return run scores where only the field values differ between runs."""
    one = Score(correct=1, total=1)
    return RunScores(
        record_recall=one,
        record_precision=one,
        field_values=Score(correct=field_correct, total=4),
        field_status=one,
        citations=one,
        seeded_errors_caught=Score(),
        correct_values_flagged=Score(correct=0, total=1),
    )


def make_case(case_id: str, tags: list[str]) -> EvalCase:
    """Return a loaded synthetic case with no documents read."""
    info = EvalCaseInfo(
        id=case_id,
        description="synthetic",
        source="synthetic",
        tags=tags,
        labeled_by="synthetic",
        labeled_on="2026-10-20",
        field_rules_version="0.3",
    )
    expected = ExpectedExtraction(records=[])
    return EvalCase.model_validate(
        {"folder": Path(case_id), "info": info, "expected": expected, "seeded": {}, "documents": []}
    )


def make_case_with_runs(case_id: str, tags: list[str], field_counts: list[int]) -> CaseResult:
    """Return a case result with one run per field-values count (out of 4)."""
    runs = [
        make_run_result(
            index,
            RunOutcome(run_id=f"run_eval_{index:04d}", status="in_review"),
            RunScoring(
                scores=make_scores(count),
                records=[],
                by_field={"key_a": FieldTally(values=Score(correct=count, total=4))},
                unmatched_expected=[],
                unmatched_actual=[],
                seeded_errors=[],
            ),
        )
        for index, count in enumerate(field_counts, start=1)
    ]
    outcome = CaseOutcome(provider="fake", models={}, runs=[])
    return make_case_result(make_case(case_id, tags), outcome, runs)


def make_report(bundle: ConfigBundle, cases: list[CaseResult]) -> SuiteReport:
    """Return a suite report over the given case results."""
    return SuiteReport(
        suite="cases",
        started_at=STARTED,
        finished_at=STARTED,
        runs_per_case=3,
        config_versions=bundle.versions(),
        unscored_fields=["key_unscored"],
        cases=cases,
        case_problems=[],
        by_tag=summarize_tags(cases),
        by_field=summarize_fields(cases),
    )


def test_case_summary_shows_the_spread_over_runs() -> None:
    """Each score gets mean, min and max over the runs; uncounted scores stay empty."""
    case = make_case_with_runs("synthetic_a", ["tag_a"], [2, 3, 4])
    spread = case.summary["field_values"]
    assert spread.mean == 0.75
    assert (spread.minimum, spread.maximum, spread.runs_scored) == (0.5, 1.0, 3)
    assert case.summary["seeded_errors_caught"].mean is None
    assert list(case.summary) == SCORE_NAMES


def test_tags_and_fields_are_summarized_over_cases() -> None:
    """A tag's score is the mean of its cases' means; field tallies add up over all runs."""
    first = make_case_with_runs("synthetic_a", ["shared", "only_a"], [4])
    second = make_case_with_runs("synthetic_b", ["shared"], [2])
    tags = summarize_tags([first, second])
    assert tags["shared"]["field_values"] == 0.75
    assert tags["only_a"]["field_values"] == 1.0
    fields = summarize_fields([first, second])
    assert fields["key_a"].values == Score(correct=6, total=8)


def test_report_files_have_the_documented_shape(bundle: ConfigBundle, tmp_path: Path) -> None:
    """JSON holds versions and scores by case, run, record, field and tag; CSV one row per score."""
    report = make_report(bundle, [make_case_with_runs("synthetic_a", ["tag_a"], [3, 4])])
    json_path, csv_path = write_report(report, tmp_path)
    assert json_path.name == "20261020T120000Z_cases.json"
    assert csv_path.name == "20261020T120000Z_cases.csv"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert set(data) >= {"config_versions", "cases", "by_tag", "by_field", "unscored_fields"}
    assert data["config_versions"]["field_rules"] == bundle.field_rules.version
    run = data["cases"][0]["runs"][0]
    assert set(run) >= {"scores", "records", "by_field", "unmatched_expected", "seeded_errors"}
    assert run["scores"]["field_values"] == {"correct": 3, "total": 4, "rate": 0.75}
    with csv_path.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert list(rows[0]) == CSV_COLUMNS
    case_rows = [row for row in rows if row["level"] == "case"]
    assert len(case_rows) == len(SCORE_NAMES)
    field_row = next(row for row in case_rows if row["score"] == "field_values")
    assert (field_row["mean"], field_row["minimum"], field_row["maximum"]) == (
        "0.875",
        "0.750",
        "1.000",
    )
    assert {row["level"] for row in rows} == {"case", "tag", "field"}


def test_report_reads_back_as_a_suite_report(bundle: ConfigBundle, tmp_path: Path) -> None:
    """The JSON file parses back into the report model."""
    report = make_report(bundle, [make_case_with_runs("synthetic_a", [], [4])])
    json_path, _ = write_report(report, tmp_path)
    loaded = SuiteReport.model_validate_json(json_path.read_text(encoding="utf-8"))
    assert loaded.cases[0].case_id == "synthetic_a"
