"""Review routes (CONTRACTS §13): view, fields, record, source, page image, bulk preview.

Bulk actions, changes, re-check and Verify are here too.

Thin: each route calls a run query or the review service with the run's own review context.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from app.api.auth import CurrentUser
from app.api.dependencies import WorkspaceDependency, current_time
from app.api.errors import error_responses
from app.contracts.api import BulkActionSummary, ChunkSource, RecordDetail, RunFieldList
from app.contracts.changes import ChangesRequest
from app.review import service
from app.review.bulk_preview import BulkMode, BulkPreview, BulkRequest
from app.review.view import ReviewView
from app.runs.contexts import load_review_context
from app.runs.fields import list_run_fields
from app.runs.queries import (
    build_run_view,
    find_chunk_source,
    find_page_image,
    find_record_detail,
    list_run_bulk_actions,
    preview_bulk_change,
)

router = APIRouter(prefix="/runs", tags=["review"], responses=error_responses(403, 500, 503))

PNG_MEDIA_TYPE = "image/png"

# The OpenAPI entry of a page image
PNG_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {"content": {PNG_MEDIA_TYPE: {}}, "description": "The scanned page as a PNG image"}
}


@router.get("/{run_id}/records", summary="Get the review view", responses=error_responses(404, 422))
def get_review_view(user: CurrentUser, workspace: WorkspaceDependency, run_id: str) -> ReviewView:
    """Return one row per record, with each cell's value, display value, color and sources.

    Placeholder fields have an empty value and the placeholder as their display value.
    """
    return build_run_view(workspace, run_id)


@router.get("/{run_id}/fields", summary="Get the run's fields", responses=error_responses(404, 422))
def get_run_fields(user: CurrentUser, workspace: WorkspaceDependency, run_id: str) -> RunFieldList:
    """Return every loader field in loader order, with the values its dropdown may offer.

    List values come from the lookup list version the run captured at its start.
    """
    return list_run_fields(workspace, run_id)


@router.get(
    "/{run_id}/records/{record_id}", summary="Get a record", responses=error_responses(404, 422)
)
def get_record(
    user: CurrentUser, workspace: WorkspaceDependency, run_id: str, record_id: str
) -> RecordDetail:
    """Return one record with all its sections, its issues and the location of its sources."""
    return find_record_detail(workspace, run_id, record_id)


@router.get(
    "/{run_id}/chunks/{chunk_id}", summary="Get a source chunk", responses=error_responses(404, 422)
)
def get_chunk(
    user: CurrentUser, workspace: WorkspaceDependency, run_id: str, chunk_id: str
) -> ChunkSource:
    """Return a chunk's text for "Show source", with its document, section and page."""
    return find_chunk_source(workspace, run_id, chunk_id)


@router.get(
    "/{run_id}/chunks/{chunk_id}/image",
    summary="Get a scanned page image",
    response_class=FileResponse,
    responses={**PNG_RESPONSE, **error_responses(404, 422)},
)
def get_chunk_image(
    user: CurrentUser, workspace: WorkspaceDependency, run_id: str, chunk_id: str
) -> FileResponse:
    """Return the PNG of a scanned-page (`page_image`) chunk; a text chunk is 404."""
    return FileResponse(find_page_image(workspace, run_id, chunk_id), media_type=PNG_MEDIA_TYPE)


@router.get(
    "/{run_id}/bulk-preview",
    summary="Preview a bulk change",
    responses=error_responses(400, 404, 409, 422),
)
def get_bulk_preview(
    user: CurrentUser,
    workspace: WorkspaceDependency,
    run_id: str,
    mode: Annotated[BulkMode, Query(description="The bulk action to preview.")],
    issue_id: Annotated[
        str | None,
        Query(description="The issue it starts from (change_all, accept_type, resolve_conflicts)."),
    ] = None,
    field: Annotated[
        str | None, Query(description="The field key whose missing values to fill (fill_missing).")
    ] = None,
    alternative_index: Annotated[
        int | None,
        Query(
            ge=0, description="The chosen alternative of the issue's record (resolve_conflicts)."
        ),
    ] = None,
) -> BulkPreview:
    """Return the records the bulk action would touch (excluded records never match)."""
    request = BulkRequest(
        mode=mode, issue_id=issue_id, field=field, alternative_index=alternative_index
    )
    return preview_bulk_change(workspace, run_id, request)


@router.get(
    "/{run_id}/bulk-actions", summary="List bulk actions", responses=error_responses(404, 422)
)
def list_bulk_actions(
    user: CurrentUser, workspace: WorkspaceDependency, run_id: str
) -> list[BulkActionSummary]:
    """Return the run's bulk actions, newest first, with whether each was or can be undone."""
    return list_run_bulk_actions(workspace.database, run_id)


@router.post(
    "/{run_id}/changes", summary="Save changes", responses=error_responses(400, 404, 409, 422)
)
def save_changes(
    user: CurrentUser, workspace: WorkspaceDependency, run_id: str, body: ChangesRequest
) -> service.SaveResult:
    """Store the changes as pending until the next re-check; a resent change ID is ignored.

    The signed-in user is stored with the changes; the body's timestamp is kept.
    """
    context = load_review_context(workspace, run_id)
    return service.save_changes(
        workspace.database, context, run_id, body.changes, user.name, body.timestamp
    )


@router.post(
    "/{run_id}/recheck", summary="Re-check a run", responses=error_responses(404, 409, 422)
)
def recheck_run(
    user: CurrentUser, workspace: WorkspaceDependency, run_id: str
) -> service.RecheckResult:
    """Apply the pending changes and run the validation; return the updated counts."""
    context = load_review_context(workspace, run_id)
    return service.recheck_run(workspace.database, context, run_id, user.name, current_time())


@router.post("/{run_id}/verify", summary="Verify a run", responses=error_responses(404, 409, 422))
def verify_run(
    user: CurrentUser, workspace: WorkspaceDependency, run_id: str
) -> service.VerifyResult:
    """Re-check, then set the verified label, or return the issues that block it."""
    context = load_review_context(workspace, run_id)
    return service.verify_run(workspace.database, context, run_id, user.name, current_time())
