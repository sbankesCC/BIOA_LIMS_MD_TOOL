"""Eval report: per-run scores gathered by case, tag and field, written as JSON plus a CSV summary.

Files: `evals/reports/<timestamp>_<suite>.json` (all versions, scores by record, field, case and
tag) and `<timestamp>_<suite>.csv` (one row per case, tag or field score, with the spread).
"""

import csv
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from app.config.bundle import ConfigVersions
from app.contracts.eval_case import CaseSource
from app.evals.case_loader import CaseProblem, EvalCase
from app.evals.runner import CaseOutcome, RunOutcome
from app.evals.scoring import (
    FieldTally,
    RecordResult,
    RunScores,
    RunScoring,
    Score,
    SeededResult,
)

# Report file names: <timestamp>_<suite>.json and .csv, the timestamp in UTC
TIMESTAMP_FORMAT = "%Y%m%dT%H%M%SZ"
CSV_COLUMNS = ["level", "name", "score", "mean", "minimum", "maximum", "runs_scored"]

# Score names, in report order (the fields of RunScores)
SCORE_NAMES = list(RunScores.model_fields)


class Spread(BaseModel):
    """Mean, lowest and highest rate of one score over a case's runs (None if never counted)."""

    mean: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    runs_scored: int = 0


class RunResult(BaseModel):
    """One run's status and scores, with the details behind them."""

    run_index: int
    run_id: str
    status: str
    error: str | None
    scores: RunScores
    records: list[RecordResult]
    by_field: dict[str, FieldTally]
    unmatched_expected: list[str]
    unmatched_actual: list[str]
    seeded_errors: list[SeededResult]


class CaseResult(BaseModel):
    """One case's runs and the spread of each score."""

    case_id: str
    description: str
    source: CaseSource
    tags: list[str]
    llm_provider: str
    models: dict[str, str]
    field_rules_version: str
    has_field_rules_mismatch: bool
    warnings: list[str]
    runs: list[RunResult]
    summary: dict[str, Spread]


class SuiteReport(BaseModel):
    """The whole report of one suite run."""

    suite: str
    started_at: datetime
    finished_at: datetime
    runs_per_case: int
    config_versions: ConfigVersions
    unscored_fields: list[str]
    cases: list[CaseResult]
    case_problems: list[CaseProblem]
    by_tag: dict[str, dict[str, float | None]]
    by_field: dict[str, FieldTally]


def make_run_result(run_index: int, outcome: RunOutcome, scoring: RunScoring) -> RunResult:
    """Combine a run's outcome and its scoring."""
    return RunResult(
        run_index=run_index,
        run_id=outcome.run_id,
        status=outcome.status,
        error=outcome.error,
        scores=scoring.scores,
        records=scoring.records,
        by_field=scoring.by_field,
        unmatched_expected=scoring.unmatched_expected,
        unmatched_actual=scoring.unmatched_actual,
        seeded_errors=scoring.seeded_errors,
    )


def make_case_result(case: EvalCase, outcome: CaseOutcome, runs: list[RunResult]) -> CaseResult:
    """Build a case's result with the spread of each score over its runs."""
    return CaseResult(
        case_id=case.info.id,
        description=case.info.description,
        source=case.info.source,
        tags=case.info.tags,
        llm_provider=outcome.provider,
        models=outcome.models,
        field_rules_version=case.info.field_rules_version,
        has_field_rules_mismatch=case.has_field_rules_mismatch,
        warnings=case.warnings,
        runs=runs,
        summary={name: summarize_score(runs, name) for name in SCORE_NAMES},
    )


def summarize_score(runs: Sequence[RunResult], name: str) -> Spread:
    """Return the spread of one score's rate over the runs where it was counted."""
    rates = [rate for run in runs if (rate := getattr(run.scores, name).rate) is not None]
    if not rates:
        return Spread()
    return Spread(
        mean=sum(rates) / len(rates), minimum=min(rates), maximum=max(rates), runs_scored=len(rates)
    )


def summarize_tags(cases: Sequence[CaseResult]) -> dict[str, dict[str, float | None]]:
    """Return, per tag, the mean of each score's case means over the cases with that tag."""
    tags = sorted({tag for case in cases for tag in case.tags})
    summary: dict[str, dict[str, float | None]] = {}
    for tag in tags:
        tagged = [case for case in cases if tag in case.tags]
        summary[tag] = {name: mean_of_case_means(tagged, name) for name in SCORE_NAMES}
    return summary


def mean_of_case_means(cases: Sequence[CaseResult], name: str) -> float | None:
    """Return the mean of one score's case means, skipping cases where it was never counted."""
    means = [mean for case in cases if (mean := case.summary[name].mean) is not None]
    return sum(means) / len(means) if means else None


def summarize_fields(cases: Sequence[CaseResult]) -> dict[str, FieldTally]:
    """Sum each field's value and status scores over every run of every case."""
    totals: dict[str, FieldTally] = {}
    for case in cases:
        for run in case.runs:
            for key, tally in run.by_field.items():
                total = totals.get(key, FieldTally())
                totals[key] = FieldTally(
                    values=total.values.add(tally.values), status=total.status.add(tally.status)
                )
    return totals


def make_csv_rows(report: SuiteReport) -> list[dict[str, object]]:
    """Return the CSV summary rows: each case score (with spread), tag score and field score."""
    rows: list[dict[str, object]] = []
    for case in report.cases:
        for name, spread in case.summary.items():
            rows.append(make_row("case", case.case_id, name, spread))
    for tag, scores in report.by_tag.items():
        for name, mean in scores.items():
            rows.append(make_row("tag", tag, name, Spread(mean=mean)))
    for key, tally in report.by_field.items():
        rows.append(make_row("field", key, "field_values", rate_spread(tally.values)))
        rows.append(make_row("field", key, "field_status", rate_spread(tally.status)))
    return rows


def rate_spread(score: Score) -> Spread:
    """Return a summed score's rate as a spread with only the mean set."""
    return Spread(mean=score.rate)


def make_row(level: str, name: str, score: str, spread: Spread) -> dict[str, object]:
    """Return one CSV row; empty cells where a value was never counted."""
    return {
        "level": level,
        "name": name,
        "score": score,
        "mean": format_rate(spread.mean),
        "minimum": format_rate(spread.minimum),
        "maximum": format_rate(spread.maximum),
        "runs_scored": spread.runs_scored if level == "case" else "",
    }


def format_rate(rate: float | None) -> str:
    """Return a rate with three decimals, or empty text when there is none."""
    return "" if rate is None else f"{rate:.3f}"


def write_report(report: SuiteReport, reports_dir: Path) -> tuple[Path, Path]:
    """Write the JSON report and the CSV summary; return both paths."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{report.started_at.strftime(TIMESTAMP_FORMAT)}_{Path(report.suite).name}"
    json_path = reports_dir / f"{stem}.json"
    csv_path = reports_dir / f"{stem}.csv"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    # newline="" lets the csv module write its own line endings
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(make_csv_rows(report))
    return json_path, csv_path
