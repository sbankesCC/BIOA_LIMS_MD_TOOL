"""API request and response models (CONTRACTS §13) not defined by the other contracts.

The OpenAPI schema is generated from these and the models they reuse (records, issues,
changes, exports, the review view), so the front end's API types follow them.
"""

from datetime import datetime
from typing import Annotated

from pydantic import JsonValue, StringConstraints

from app.config.bundle import ConfigVersions
from app.contracts.base import ContractModel
from app.contracts.chunk import ChunkKind
from app.contracts.export import ExportInfo
from app.contracts.issue import Issue
from app.contracts.record import StoredRecord
from app.contracts.run import RunStatus
from app.ingest.file_types import FileType
from app.review.view import ReviewCounts, SourceLocation
from app.storage.review_db import DataVersion
from app.storage.run_store import DocumentStatus

# A run name: surrounding spaces removed, never empty
RunName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class ErrorBody(ContractModel):
    """What went wrong: a stable code, a plain message that says what to do, and details."""

    code: str
    message: str
    details: dict[str, JsonValue] = {}


class ErrorResponse(ContractModel):
    """Every error response has this shape."""

    error: ErrorBody


class StartRunResponse(ContractModel):
    """A run that was stored and queued for processing; follow it with `GET /runs/{run_id}`."""

    run_id: str
    retry_of: str | None = None


class RenameRunRequest(ContractModel):
    """The body of `PATCH /runs/{run_id}`."""

    name: RunName


class RunSummary(ContractModel):
    """One run in the runs list: name, status, counts and the verified label."""

    run_id: str
    name: str
    created_by: str
    created_at: datetime
    status: RunStatus
    retry_of: str | None
    is_verified: bool
    verified_by: str | None
    verified_at: datetime | None
    counts: ReviewCounts


class RunDocument(ContractModel):
    """One uploaded document of a run (never its contents)."""

    document_id: str
    file_name: str
    file_type: FileType
    size_bytes: int
    page_count: int | None
    status: DocumentStatus


class RunDetail(ContractModel):
    """One run: status, current step, verified label, versions, documents, exports, run issues.

    `current_step` is the processing status while the graph works, else null.
    """

    run_id: str
    name: str
    created_by: str
    created_at: datetime
    status: RunStatus
    current_step: RunStatus | None
    retry_of: str | None
    is_verified: bool
    verified_by: str | None
    verified_at: datetime | None
    config_versions: ConfigVersions
    reference_data_version: str | None
    models: dict[str, str]
    has_pending_changes: bool
    counts: ReviewCounts
    documents: list[RunDocument]
    run_issues: list[Issue]
    exports: list[ExportInfo]


class RecordDetail(ContractModel):
    """One record with all its sections, its issues (any status) and its resolved sources."""

    record: StoredRecord
    issues: list[Issue]
    sources: list[SourceLocation]


class ChunkSource(ContractModel):
    """A chunk's text for "Show source", with its document, section and page.

    A scanned page has no text (`kind` is `page_image`).
    """

    chunk_id: str
    kind: ChunkKind
    text: str | None
    location: SourceLocation


class DataVersionList(ContractModel):
    """Version history of lookup lists or reference data, and the version new runs use."""

    current_version: str | None
    versions: list[DataVersion]
