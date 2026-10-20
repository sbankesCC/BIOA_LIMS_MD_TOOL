"""Log line (CONTRACTS §11): one JSON log line with IDs, counts and durations only."""

from datetime import datetime

from app.contracts.base import ContractModel
from app.logging_setup import DetailValue, LogEvent, LogLevel


class LogLine(ContractModel):
    """One application log line; details hold numbers only, never text or field values."""

    timestamp: datetime
    level: LogLevel
    event: LogEvent
    run_id: str | None = None
    node: str | None = None
    attempt: int | None = None
    duration_ms: int | None = None
    details: dict[str, DetailValue] | None = None
