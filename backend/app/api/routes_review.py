"""Review routes (CONTRACTS §13): view, record, source chunk, bulk preview, changes, Verify.

Thin: each route calls a run query or the review service with the run's own review context.
Re-check and Verify are here too.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.auth import CurrentUser
from app.api.dependencies import WorkspaceDependency, current_time
from app.api.errors import error_responses
from app.contracts.api import ChunkSource, RecordDetail
from app.contracts.changes import ChangesRequest
from app.review import service
from app.review.bulk_preview import BulkPreview
from app.review.view import ReviewView
from app.runs.contexts import load_review_context
from app.runs.queries import (
    build_run_view,
    find_chunk_source,
    find_record_detail,
    preview_bulk_change,
)

router = APIRouter(prefix="/runs", tags=["review"], responses=error_responses(403, 500, 503))


@router.get("/{run_id}/records", summary="Get the review view", responses=error_responses(404, 422))
def get_review_view(user: CurrentUser, workspace: WorkspaceDependency, run_id: str) -> ReviewView:
    """Return one row per record, with each cell's value, display value, color and sources.

    Placeholder fields have an empty value and the placeholder as their display value.
    """
    return build_run_view(workspace, run_id)


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
    "/{run_id}/bulk-preview",
    summary="Preview a bulk change",
    responses=error_responses(400, 404, 409, 422),
)
def get_bulk_preview(
    user: CurrentUser,
    workspace: WorkspaceDependency,
    run_id: str,
    issue_id: Annotated[str, Query(description="The issue the bulk change starts from.")],
) -> BulkPreview:
    """Return the records with an open issue of the same code, on the same field, same value."""
    return preview_bulk_change(workspace, run_id, issue_id)


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
