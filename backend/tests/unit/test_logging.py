"""Tests for structured logging: JSON lines with IDs, counts and durations only."""

import json
import logging

import pytest

from app.logging_setup import LOGGER_NAME, build_log_line, log_event, setup_logging


def test_log_line_has_contract_fields() -> None:
    """A log line holds timestamp, level, event, IDs, duration and numeric details."""
    line = build_log_line(
        "node_finished",
        run_id="run_0001",
        node="extraction",
        attempt=1,
        duration_ms=250,
        details={"records_found": 3},
    )
    assert line["event"] == "node_finished"
    assert line["level"] == "INFO"
    assert line["run_id"] == "run_0001"
    assert line["details"] == {"records_found": 3}
    assert str(line["timestamp"]).endswith("Z")


def test_unset_fields_are_left_out() -> None:
    """Fields that were not given do not appear in the line."""
    line = build_log_line("run_started", run_id="run_0001")
    assert set(line) == {"timestamp", "level", "event", "run_id"}


def test_text_details_are_rejected() -> None:
    """Details must be counts or durations, so a text value is refused."""
    with pytest.raises(ValueError, match="must be a count or duration"):
        build_log_line("node_finished", details={"name": "synthetic text"})  # pyright: ignore[reportArgumentType]


def test_log_event_writes_one_json_line(caplog: pytest.LogCaptureFixture) -> None:
    """log_event writes a single parseable JSON line to the app logger."""
    setup_logging()
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        log_event("run_started", run_id="run_0001")
    assert json.loads(caplog.records[-1].getMessage())["run_id"] == "run_0001"
