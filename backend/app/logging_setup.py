"""Structured JSON-lines application logging (CONTRACTS §11).

Log lines hold IDs, counts and durations only: never document text or field values.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Literal

LOGGER_NAME = "app"

LogEvent = Literal[
    "run_started",
    "node_started",
    "node_finished",
    "node_failed",
    "retry_scheduled",
    "route_decided",
    "llm_call_finished",
    "changes_saved",
    "run_rechecked",
    "run_verified",
    "export_created",
    "lookup_version_applied",
    "reference_data_applied",
]

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]

# Details carry counts and durations only, so their values must be numbers
DetailValue = int | float


class JsonLineFormatter(logging.Formatter):
    """Write each record's message as-is: `log_event` has already built the JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        """Return the prepared JSON line."""
        return record.getMessage()


def setup_logging(level: int = logging.INFO) -> None:
    """Send app log lines to stderr as JSON lines; safe to call more than once."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(JsonLineFormatter())
        logger.addHandler(handler)


def build_log_line(
    event: LogEvent,
    level: LogLevel = "INFO",
    run_id: str | None = None,
    node: str | None = None,
    attempt: int | None = None,
    duration_ms: int | None = None,
    details: dict[str, DetailValue] | None = None,
) -> dict[str, object]:
    """Build one log line as a dict, leaving out fields that are not set."""
    # Booleans pass an int check in Python, but they are not counts or durations
    for key, value in (details or {}).items():
        if type(value) not in (int, float):
            raise ValueError(f"Log detail '{key}' must be a count or duration (a number).")
    line: dict[str, object] = {
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "level": level,
        "event": event,
        "run_id": run_id,
        "node": node,
        "attempt": attempt,
        "duration_ms": duration_ms,
        "details": details,
    }
    return {key: value for key, value in line.items() if value is not None}


def log_event(
    event: LogEvent,
    level: LogLevel = "INFO",
    run_id: str | None = None,
    node: str | None = None,
    attempt: int | None = None,
    duration_ms: int | None = None,
    details: dict[str, DetailValue] | None = None,
) -> None:
    """Write one structured log line (CONTRACTS §11)."""
    line = build_log_line(event, level, run_id, node, attempt, duration_ms, details)
    level_number = logging.getLevelNamesMapping()[level]
    logging.getLogger(LOGGER_NAME).log(level_number, json.dumps(line))
