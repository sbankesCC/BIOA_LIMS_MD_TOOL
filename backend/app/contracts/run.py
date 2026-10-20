"""Run and audit event (CONTRACTS §7): the `runs` and `audit_events` rows of the review database.

LangGraph processing state is not here: it lives with the graph (`graph/state.py`).
"""

from datetime import datetime
from typing import Literal

from pydantic import JsonValue

from app.config.bundle import ConfigVersions
from app.contracts.base import ContractModel

# Run lifecycle (ARCHITECTURE §6); the verified label is kept separately
RunStatus = Literal[
    "created",
    "ingesting",
    "extracting",
    "verifying_extraction",
    "transforming",
    "validating",
    "in_review",
    "rechecking",
    "failed",
]


class RunInfo(ContractModel):
    """One run: name, who started it, config versions captured at start, status, verified label.

    `models` names the LLM model used per node (e.g. extraction), captured at start like the
    config versions, so the audit file can list them.
    """

    run_id: str
    name: str
    created_by: str
    created_at: datetime
    config_versions: ConfigVersions
    reference_data_version: str | None = None
    models: dict[str, str] = {}
    retry_of: str | None = None
    status: RunStatus = "created"
    is_verified: bool = False
    verified_by: str | None = None
    verified_at: datetime | None = None


class AuditEvent(ContractModel):
    """One business event for the audit trail (verification, export, exclusion, admin action)."""

    event: str
    run_id: str | None
    by: str
    at: datetime
    details: dict[str, JsonValue] = {}
