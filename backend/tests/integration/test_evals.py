"""Eval harness end to end: the synthetic case runs through the graph with its fake replies.

Proves the plumbing (graph, seeding, scoring, report), not extraction quality. No network.
"""

import json
from pathlib import Path

import pytest

from app.config.bundle import ConfigBundle
from app.evals.__main__ import main
from app.evals.case_loader import EVALS_DIR, load_scoring_config
from app.evals.report import SuiteReport
from app.evals.scoring import Score
from app.evals.suite import run_suite
from app.settings import Settings
from tests.conftest import CLIENT_CONFIG_DIR

CASES_DIR = EVALS_DIR / "cases"


@pytest.fixture(scope="module")
def suite_report(bundle: ConfigBundle, tmp_path_factory: pytest.TempPathFactory) -> SuiteReport:
    """Run the committed cases suite once (3 runs per case) in a temp work folder."""
    work_dir = tmp_path_factory.mktemp("eval_work")
    return run_suite(CASES_DIR, bundle, Settings(), load_scoring_config(), work_dir, runs=3)


def test_synthetic_case_runs_three_times_to_review(suite_report: SuiteReport) -> None:
    """Each of the 3 runs ends in review on the fake provider, with no error."""
    [case] = suite_report.cases
    assert case.case_id == "synthetic_001"
    assert case.llm_provider == "fake"
    assert [run.status for run in case.runs] == ["in_review"] * 3
    assert [run.error for run in case.runs] == [None] * 3
    assert len({run.run_id for run in case.runs}) == 3


def test_synthetic_case_scores_match_its_labels(suite_report: SuiteReport) -> None:
    """The fake replies miss one labeled value (see the case notes); everything else is right."""
    scores = suite_report.cases[0].runs[0].scores
    assert scores.record_recall == Score(correct=3, total=3)
    assert scores.record_precision == Score(correct=3, total=3)
    assert scores.field_values == Score(correct=37, total=38)
    assert scores.field_status == Score(correct=37, total=38)
    assert scores.citations == Score(correct=4, total=4)
    assert scores.seeded_errors_caught == Score(correct=1, total=1)
    assert scores.correct_values_flagged.correct == 0


def test_runs_give_the_same_scores_with_fake_replies(suite_report: SuiteReport) -> None:
    """Fake replies are deterministic, so the spread is zero."""
    for spread in suite_report.cases[0].summary.values():
        assert spread.minimum == spread.maximum


def test_description_label_is_not_scored(suite_report: SuiteReport) -> None:
    """The case labels description, but it is unscored, so it never appears in field scores."""
    assert "description" in suite_report.unscored_fields
    assert "description" not in suite_report.by_field


def test_command_writes_reports_and_leaves_app_data_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`run --suite cases` writes JSON + CSV and never creates the app's storage or databases."""
    app_data = tmp_path / "app_data"
    monkeypatch.setenv("CLIENT_CONFIG_DIR", str(CLIENT_CONFIG_DIR))
    for name in ("STORAGE_DIR", "REVIEW_DB", "CHECKPOINT_DB"):
        monkeypatch.setenv(name, str(app_data / name.lower()))
    reports_dir = tmp_path / "reports"
    exit_code = main(["run", "--suite", "cases", "--runs", "1", "--reports-dir", str(reports_dir)])
    assert exit_code == 0
    assert sorted(path.suffix for path in reports_dir.iterdir()) == [".csv", ".json"]
    report = json.loads(next(reports_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert report["runs_per_case"] == 1
    assert not app_data.exists()
    assert "Case synthetic_001" in capsys.readouterr().out


def test_command_names_a_missing_config_setting(
    blank_environment: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """With CLIENT_CONFIG_DIR blank the command stops with a message naming it."""
    monkeypatch.setattr("app.evals.__main__.load_settings", Settings)
    assert main(["run", "--suite", "cases"]) == 1
    assert "CLIENT_CONFIG_DIR" in capsys.readouterr().err
