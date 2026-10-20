"""Processing state (CONTRACTS §7): what LangGraph checkpoints while a run is processed.

References only: document and chunk IDs, never chunk text or page images (those stay in the run
store). Records, issues and findings are kept as plain JSON so any checkpointer can store them.
"""

from collections.abc import Sequence
from typing import Any, TypedDict

from pydantic import TypeAdapter

from app.contracts.extraction import ExcludedItem
from app.contracts.issue import Issue
from app.contracts.record import StoredRecord
from app.contracts.verification import VerificationOutput

JsonObject = dict[str, Any]

RECORD_MAP = TypeAdapter(dict[str, StoredRecord])
ISSUE_LIST = TypeAdapter(list[Issue])
EXCLUDED_ITEM_LIST = TypeAdapter(list[ExcludedItem])


class ProcessingState(TypedDict):
    """The checkpointed state of one run; `failure_code` is set when the run must fail."""

    run_id: str
    config_versions: JsonObject
    max_reextract: int
    document_ids: list[str]
    chunk_ids: list[str]
    records: dict[str, JsonObject]
    excluded_items: list[JsonObject]
    findings: JsonObject | None
    dropped_record_ids: list[str]
    reextract_count: int
    issues: list[JsonObject]
    failure_code: str | None


def make_initial_state(
    run_id: str, config_versions: JsonObject, max_reextract: int
) -> ProcessingState:
    """Return the state a run starts with: its ID, captured versions and re-extraction limit."""
    return ProcessingState(
        run_id=run_id,
        config_versions=config_versions,
        max_reextract=max_reextract,
        document_ids=[],
        chunk_ids=[],
        records={},
        excluded_items=[],
        findings=None,
        dropped_record_ids=[],
        reextract_count=0,
        issues=[],
        failure_code=None,
    )


def read_records(state: ProcessingState) -> list[StoredRecord]:
    """Return the state's records in order."""
    return list(RECORD_MAP.validate_python(state["records"]).values())


def dump_records(records: Sequence[StoredRecord]) -> dict[str, JsonObject]:
    """Return records as state JSON, keyed by record ID, in order."""
    return {record.record_id: record.model_dump(mode="json") for record in records}


def read_issues(state: ProcessingState) -> list[Issue]:
    """Return the state's issues."""
    return ISSUE_LIST.validate_python(state["issues"])


def dump_issues(issues: Sequence[Issue]) -> list[JsonObject]:
    """Return issues as state JSON."""
    return [issue.model_dump(mode="json") for issue in issues]


def read_excluded_items(state: ProcessingState) -> list[ExcludedItem]:
    """Return the items extraction left out."""
    return EXCLUDED_ITEM_LIST.validate_python(state["excluded_items"])


def dump_excluded_items(items: Sequence[ExcludedItem]) -> list[JsonObject]:
    """Return excluded items as state JSON."""
    return [item.model_dump(mode="json") for item in items]


def read_findings(state: ProcessingState) -> VerificationOutput | None:
    """Return the latest extraction verification findings, or None before verification."""
    findings = state["findings"]
    return None if findings is None else VerificationOutput.model_validate(findings)
