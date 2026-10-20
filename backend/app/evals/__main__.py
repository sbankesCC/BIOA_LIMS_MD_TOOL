"""Eval harness command line: `uv run python -m app.evals run --suite cases` (from the repo root).

`--suite` is a folder under `evals/` at the repo root (or an absolute path). Reports go to
`evals/reports/`. Eval runs work in a temporary folder unless `--work-dir` names one to keep.
"""

import argparse
import logging
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from app.config.bundle import load_config_bundle
from app.config.errors import ConfigError
from app.evals.case_loader import (
    REPORTS_DIR,
    CaseLoadError,
    load_scoring_config,
    resolve_suite_dir,
)
from app.evals.report import write_report
from app.evals.suite import DEFAULT_RUNS, format_summary, run_suite
from app.llm.provider import LLMProviderError
from app.logging_setup import setup_logging
from app.settings import MissingSettingError, Settings, load_settings

# Errors that stop the harness with their plain message instead of a traceback
STOPPING_ERRORS = (MissingSettingError, ConfigError, CaseLoadError, LLMProviderError)


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser with its `run` command."""
    parser = argparse.ArgumentParser(prog="python -m app.evals", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Run a suite of eval cases and write a report.")
    run.add_argument("--suite", required=True, help="Suite folder under evals/, e.g. cases.")
    run.add_argument("--runs", type=int, default=DEFAULT_RUNS, help="Runs per case.")
    run.add_argument(
        "--real-llm",
        action="store_true",
        help="Use LLM_PROVIDER even for cases that have fake replies (fake_llm/).",
    )
    run.add_argument("--reports-dir", type=Path, default=REPORTS_DIR, help="Report folder.")
    run.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="New, empty folder to keep the runs' files in (default: a temporary folder).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command; return 0 on success, 1 when something must be fixed first."""
    arguments = build_parser().parse_args(argv)
    # The graph's info lines would drown the summary; warnings and errors still show
    setup_logging(logging.WARNING)
    try:
        return run_command(arguments, load_settings())
    except STOPPING_ERRORS as error:
        print(str(error), file=sys.stderr)
        return 1


def run_command(arguments: argparse.Namespace, settings: Settings) -> int:
    """Load the config, run the suite in its work folder, write and summarize the report."""
    bundle = load_config_bundle(settings.require_path("CLIENT_CONFIG_DIR"))
    suite_dir = resolve_suite_dir(arguments.suite)
    scoring_config = load_scoring_config()
    work_dir: Path | None = arguments.work_dir
    if work_dir is not None and work_dir.exists() and any(work_dir.iterdir()):
        print(f"The work folder {work_dir} is not empty. Name a new folder.", file=sys.stderr)
        return 1
    # Without --work-dir the runs' files go to a temporary folder, deleted at the end
    with tempfile.TemporaryDirectory(prefix="eval_work_", ignore_cleanup_errors=True) as temporary:
        report = run_suite(
            suite_dir,
            bundle,
            settings,
            scoring_config,
            work_dir or Path(temporary),
            arguments.runs,
            arguments.real_llm,
        )
    paths = write_report(report, arguments.reports_dir)
    print("\n".join(format_summary(report, paths)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
