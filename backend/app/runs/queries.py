"""Run queries for the API: runs, run detail, review view, record, chunk, bulk preview, exports.

Also the stored PNG of a scanned page and a run's bulk actions.

Read only: nothing here changes a run.
"""

from collections.abc import Sequence
from pathlib import Path, PurePath
from typing import Literal

from app.contracts.api import (
    BulkActionSummary,
    ChunkSource,
    RecordDetail,
    RunDetail,
    RunDocument,
    RunExport,
    RunSummary,
)
from app.contracts.chunk import Chunk
from app.contracts.export import ExportInfo
from app.contracts.issue import Issue
from app.contracts.record import StoredRecord
from app.contracts.run import RunInfo, RunStatus
from app.review.bulk_actions import list_bulk_actions
from app.review.bulk_preview import BulkPreview, BulkRequest, find_bulk_matches
from app.review.view import ReviewCounts, ReviewView, SourceLocator, build_review_view, count_review
from app.runs.errors import RunRequestError
from app.runs.workspace import Workspace
from app.storage.review_db import ReviewDatabase
from app.storage.run_store import DocumentInfo, RunFolder

# Statuses while the graph works; the run detail shows them as the current step
PROCESSING_STATUSES: frozenset[RunStatus] = frozenset(
    {"created", "ingesting", "extracting", "verifying_extraction", "transforming", "validating"}
)

ExportFileKind = Literal["loader", "audit"]


# ----- Runs -----


def count_run(database: ReviewDatabase, run_id: str) -> ReviewCounts:
    """Count a run's records and open issues (all zero while it is processing)."""
    return count_review(database.read_records(run_id), database.read_issues(run_id))


def summarize_run(database: ReviewDatabase, run: RunInfo) -> RunSummary:
    """Return a run's line in the runs list, with why it failed and its newest export."""
    exports = database.list_exports(run.run_id)
    return RunSummary(
        run_id=run.run_id,
        name=run.name,
        created_by=run.created_by,
        created_at=run.created_at,
        status=run.status,
        retry_of=run.retry_of,
        is_verified=run.is_verified,
        verified_by=run.verified_by,
        verified_at=run.verified_at,
        counts=count_run(database, run.run_id),
        failure_reason=find_failure_reason(database, run),
        latest_export=make_run_export(max(exports, key=lambda e: e.number)) if exports else None,
    )


def find_failure_reason(database: ReviewDatabase, run: RunInfo) -> str | None:
    """Return the message of a failed run's first error run issue; None for other runs."""
    if run.status != "failed":
        return None
    errors = [issue for issue in find_run_issues(database, run.run_id) if issue.severity == "error"]
    return errors[0].message if errors else None


def list_run_summaries(database: ReviewDatabase) -> list[RunSummary]:
    """Return every run, newest first."""
    return [summarize_run(database, run) for run in database.list_runs()]


def describe_run(workspace: Workspace, run_id: str) -> RunDetail:
    """Return a run's status, current step, label, versions, documents, exports and run issues."""
    database = workspace.database
    run = database.read_run(run_id)
    folder = workspace.run_store.open_run(run_id)
    return RunDetail(
        run_id=run.run_id,
        name=run.name,
        created_by=run.created_by,
        created_at=run.created_at,
        status=run.status,
        current_step=run.status if run.status in PROCESSING_STATUSES else None,
        retry_of=run.retry_of,
        is_verified=run.is_verified,
        verified_by=run.verified_by,
        verified_at=run.verified_at,
        config_versions=run.config_versions,
        reference_data_version=run.reference_data_version,
        models=run.models,
        has_pending_changes=bool(database.read_changes(run_id, "pending")),
        counts=count_run(database, run_id),
        documents=[make_run_document(document) for document in folder.read_documents()],
        run_issues=find_run_issues(database, run_id),
        exports=[make_run_export(export) for export in database.list_exports(run_id)],
    )


def find_run_issues(database: ReviewDatabase, run_id: str) -> list[Issue]:
    """Return a run's run-level issues that are still shown (open or accepted)."""
    return [
        issue
        for issue in database.read_issues(run_id)
        if issue.record_id is None and issue.status != "resolved"
    ]


def make_run_document(document: DocumentInfo) -> RunDocument:
    """Return what the API shows of an uploaded document (no storage paths)."""
    return RunDocument(
        document_id=document.document_id,
        file_name=document.file_name,
        file_type=document.file_type,
        size_bytes=document.size_bytes,
        page_count=document.page_count,
        status=document.status,
    )


# ----- Review view, records and sources -----


def read_chunks(folder: RunFolder) -> list[Chunk]:
    """Return a run's chunks, or none before ingest has written them."""
    return folder.read_chunks() if folder.chunks_file.is_file() else []


def build_run_view(workspace: Workspace, run_id: str) -> ReviewView:
    """Return the flattened review view of a run (empty rows while it is processing)."""
    database = workspace.database
    database.read_run(run_id)
    folder = workspace.run_store.open_run(run_id)
    return build_review_view(
        database.read_records(run_id),
        database.read_issues(run_id),
        workspace.bundle.field_rules,
        read_chunks(folder),
        folder.read_documents(),
    )


def find_record_detail(workspace: Workspace, run_id: str, record_id: str) -> RecordDetail:
    """Return one record with its issues (any status) and the location of every cited chunk."""
    database = workspace.database
    database.read_run(run_id)
    record = next((r for r in database.read_records(run_id) if r.record_id == record_id), None)
    if record is None:
        raise RunRequestError(
            "RECORD_NOT_FOUND", f"Record {record_id} is not in run {run_id}. Reload the run."
        )
    folder = workspace.run_store.open_run(run_id)
    locator = SourceLocator(read_chunks(folder), folder.read_documents())
    issues = [issue for issue in database.read_issues(run_id) if issue.record_id == record_id]
    sources = [locator.locate(chunk_id) for chunk_id in find_cited_chunk_ids(record)]
    return RecordDetail(record=record, issues=issues, sources=sources)


def find_cited_chunk_ids(record: StoredRecord) -> list[str]:
    """Return every chunk the record cites (found in, evidence, alternatives), first seen first."""
    chunk_ids = list(record.found_in)
    for field in record.fields.values():
        if field.extraction is None:
            continue
        evidence = list(field.extraction.evidence)
        for alternative in field.extraction.alternatives:
            evidence.extend(alternative.evidence)
        chunk_ids.extend(pair.chunk_id for pair in evidence)
    # dict keeps the first position of each chunk ID
    return list(dict.fromkeys(chunk_ids))


def find_chunk(chunks: Sequence[Chunk], chunk_id: str, run_id: str) -> Chunk:
    """Return one chunk by ID; raise RunRequestError if the run has no such chunk."""
    chunk = next((chunk for chunk in chunks if chunk.chunk_id == chunk_id), None)
    if chunk is None:
        raise RunRequestError(
            "CHUNK_NOT_FOUND", f"Source {chunk_id} is not in run {run_id}. Reload the run."
        )
    return chunk


def find_chunk_source(workspace: Workspace, run_id: str, chunk_id: str) -> ChunkSource:
    """Return one chunk's text and location for "Show source"."""
    workspace.database.read_run(run_id)
    folder = workspace.run_store.open_run(run_id)
    chunks = read_chunks(folder)
    chunk = find_chunk(chunks, chunk_id, run_id)
    locator = SourceLocator(chunks, folder.read_documents())
    return ChunkSource(
        chunk_id=chunk.chunk_id, kind=chunk.kind, text=chunk.text, location=locator.locate(chunk_id)
    )


def find_page_image(workspace: Workspace, run_id: str, chunk_id: str) -> Path:
    """Return the stored PNG of a scanned-page chunk; a text chunk has none."""
    workspace.database.read_run(run_id)
    folder = workspace.run_store.open_run(run_id)
    chunk = find_chunk(read_chunks(folder), chunk_id, run_id)
    if chunk.image_ref is None:
        raise RunRequestError(
            "PAGE_IMAGE_NOT_FOUND",
            f"Source {chunk_id} is text, not a scanned page, so it has no page image. "
            "Show its text instead.",
        )
    path = workspace.run_store.resolve_ref(chunk.image_ref)
    if not path.is_file():
        raise RunRequestError(
            "PAGE_IMAGE_NOT_FOUND",
            f"The page image of source {chunk_id} is missing from storage. Retry the run.",
        )
    return path


def preview_bulk_change(workspace: Workspace, run_id: str, request: BulkRequest) -> BulkPreview:
    """Return the records a bulk action (any of the four modes) would touch."""
    database = workspace.database
    database.read_run(run_id)
    return find_bulk_matches(
        database.read_records(run_id),
        database.read_issues(run_id),
        request,
        workspace.bundle.field_rules,
    )


def list_run_bulk_actions(database: ReviewDatabase, run_id: str) -> list[BulkActionSummary]:
    """Return a run's bulk actions, newest first, with whether each can still be undone."""
    run = database.read_run(run_id)
    return list_bulk_actions(
        database.read_changes(run_id), database.read_issues(run_id), run.status == "in_review"
    )


# ----- Exports -----


def make_run_export(export: ExportInfo) -> RunExport:
    """Return what the API shows of an export: its file names, never their storage paths."""
    return RunExport(
        export_id=export.export_id,
        number=export.number,
        is_draft=export.is_draft,
        loader_file_name=PurePath(export.loader_file).name,
        audit_file_name=PurePath(export.audit_file).name,
        exported_at=export.exported_at,
        exported_by=export.exported_by,
    )


def list_run_exports(database: ReviewDatabase, run_id: str) -> list[RunExport]:
    """Return a run's exports in number order, as the API shows them."""
    database.read_run(run_id)
    return [make_run_export(export) for export in database.list_exports(run_id)]


def find_export_file(
    workspace: Workspace, run_id: str, export_id: str, kind: ExportFileKind
) -> Path:
    """Return the path of an export's loader or audit file."""
    workspace.database.read_run(run_id)
    exports = workspace.database.list_exports(run_id)
    export = find_export(exports, export_id, run_id)
    ref = export.loader_file if kind == "loader" else export.audit_file
    path = workspace.run_store.resolve_ref(ref)
    if not path.is_file():
        raise RunRequestError(
            "EXPORT_NOT_FOUND",
            f"The {kind} file of export {export_id} is missing from storage. Export the run again.",
        )
    return path


def find_export(exports: Sequence[ExportInfo], export_id: str, run_id: str) -> ExportInfo:
    """Return one export by ID; raise RunRequestError if the run has no such export."""
    for export in exports:
        if export.export_id == export_id:
            return export
    raise RunRequestError(
        "EXPORT_NOT_FOUND", f"Export {export_id} is not in run {run_id}. Check the export list."
    )
