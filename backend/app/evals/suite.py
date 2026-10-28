"""Eval suite: loads a suite's cases, runs each several times, scores the runs, builds the report.

The CLI (`__main__.py`) calls `run_suite`, then writes the report and prints `format_summary`.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from app.config.bundle import ConfigBundle
from app.evals.case_loader import EvalCase, ScoringConfig, load_suite
from app.evals.report import (
    SCORE_NAMES,
    CaseResult,
    SuiteReport,
    make_case_result,
    make_run_result,
    summarize_fields,
    summarize_tags,
)
from app.evals.runner import EvalWorkspace, open_workspace, run_case
from app.evals.scoring import score_run, select_scored_fields
from app.settings import Settings

# Each case runs this many times by default, so the report shows the spread (evals/README.md)
DEFAULT_RUNS = 3


def run_suite(
    suite_dir: Path,
    bundle: ConfigBundle,
    settings: Settings,
    scoring_config: ScoringConfig,
    work_dir: Path,
    runs: int = DEFAULT_RUNS,
    use_real_llm: bool = False,
) -> SuiteReport:
    """Run every case of a suite `runs` times through the graph and return the scored report."""
    started_at = datetime.now(UTC)
    loaded = load_suite(suite_dir, bundle.field_rules)
    extracted_keys = [rule.key for rule in bundle.field_rules.extracted_fields()]
    scored_fields = select_scored_fields(extracted_keys, scoring_config.unscored_keys())
    workspace = open_workspace(work_dir)
    try:
        cases = [
            evaluate_case(case, bundle, settings, workspace, runs, use_real_llm, scored_fields)
            for case in loaded.cases
        ]
    finally:
        workspace.close()
    return SuiteReport(
        suite=suite_dir.name,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        runs_per_case=runs,
        config_versions=bundle.versions(),
        unscored_fields=sorted(scoring_config.unscored_keys()),
        cases=cases,
        case_problems=loaded.problems,
        by_tag=summarize_tags(cases),
        by_field=summarize_fields(cases),
    )


def evaluate_case(
    case: EvalCase,
    bundle: ConfigBundle,
    settings: Settings,
    workspace: EvalWorkspace,
    runs: int,
    use_real_llm: bool,
    scored_fields: Sequence[str],
) -> CaseResult:
    """Run one case and score each of its runs."""
    outcome = run_case(case, bundle, settings, workspace, runs, use_real_llm)
    results = [
        make_run_result(
            index,
            run,
            score_run(
                case.expected,
                run.records,
                scored_fields,
                case.seeded.errors,
                run.planted,
                run.findings,
            ),
        )
        for index, run in enumerate(outcome.runs, start=1)
    ]
    return make_case_result(case, outcome, results)


def format_summary(report: SuiteReport, report_paths: Sequence[Path]) -> list[str]:
    """Return the console summary: problems, each case's score spreads, and the report files."""
    lines = [
        f"Suite {report.suite}: {len(report.cases)} case(s), {report.runs_per_case} run(s) each"
    ]
    for problem in report.case_problems:
        lines.append(f"  Skipped {problem.folder}: {problem.message}")
    for case in report.cases:
        statuses = ", ".join(run.status for run in case.runs)
        lines.append(f"Case {case.case_id} ({case.llm_provider}; runs: {statuses})")
        lines.extend(f"  Warning: {warning}" for warning in case.warnings)
        for name in SCORE_NAMES:
            spread = case.summary[name]
            if spread.mean is None:
                lines.append(f"  {name}: not counted")
                continue
            lines.append(
                f"  {name}: mean {spread.mean:.3f} "
                f"(min {spread.minimum:.3f}, max {spread.maximum:.3f})"
            )
    lines.extend(f"Report: {path}" for path in report_paths)
    return lines
