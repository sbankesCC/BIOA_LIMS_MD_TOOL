"""API request and response models (CONTRACTS §13) not defined by the other contracts.

The OpenAPI schema is generated from these and the models they reuse (records, issues,
changes, exports, the review view), so the front end's API types follow them.
"""

from datetime import datetime
from typing import Annotated

from pydantic import JsonValue, StringConstraints

from app.admin.lookup_checks import LookupUploadReport
from app.admin.reference_data import ReferenceUploadReport
from app.config.bundle import ConfigVersions
from app.config.field_rules import FieldRole, FieldType, Requirement
from app.contracts.base import ContractModel
from app.contracts.chunk import ChunkKind
from app.contracts.issue import Issue
from app.contracts.record import StoredRecord
from app.contracts.run import RunStatus
from app.ingest.file_types import FileType
from app.review.view import ReviewCounts, SourceLocation
from app.storage.review_db import DataVersionStatus
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


class RunExport(ContractModel):
    """One export of a run as the API shows it: file names only, never storage paths.

    The files download through the export's `loader` and `audit` endpoints.
    """

    export_id: str
    number: int
    is_draft: bool
    loader_file_name: str
    audit_file_name: str
    exported_at: datetime
    exported_by: str


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
    exports: list[RunExport]


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


class RunField(ContractModel):
    """One loader field of a run's captured config, for the review screen's inputs.

    `allowed_values` comes from the run's own lookup list version for a list field, is the
    accepted values for a boolean field, and is empty for any other field.
    """

    key: str
    column: str
    role: FieldRole
    requirement: Requirement
    type: FieldType
    max_length: int | None
    has_lookup_list: bool
    is_boolean: bool
    multi_value: bool
    separator: str | None
    allowed_values: list[str]


class RunFieldList(ContractModel):
    """Every loader field of a run, in loader order, with the versions they come from."""

    field_rules_version: str
    lookup_lists_version: str
    fields: list[RunField]


class DataVersionInfo(ContractModel):
    """One admin upload of lookup lists or reference data as the API shows it (no storage path).

    `file_name` is the name the file was uploaded with; `summary` holds the check report or
    diff counts.
    """

    upload_id: str
    version_id: str | None
    status: DataVersionStatus
    file_name: str
    based_on_version: str | None
    uploaded_by: str
    uploaded_at: datetime
    applied_by: str | None
    applied_at: datetime | None
    summary: dict[str, JsonValue]


class DataVersionList(ContractModel):
    """Version history of lookup lists or reference data, and the version new runs use."""

    current_version: str | None
    versions: list[DataVersionInfo]


class LookupUploadResponse(ContractModel):
    """A lookup list upload's check report, and its pending version when it has no problems."""

    report: LookupUploadReport
    version: DataVersionInfo | None


class ReferenceUploadResponse(ContractModel):
    """A reference data upload's check report, and its pending version when it has no problems."""

    report: ReferenceUploadReport
    version: DataVersionInfo | None
