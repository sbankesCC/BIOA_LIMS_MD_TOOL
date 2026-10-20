"""Export routes (CONTRACTS §13): create an export, list exports, download the loader or audit file.

Thin: each route calls the export service or a run query.
"""

from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import FileResponse

from app.api.auth import CurrentUser
from app.api.dependencies import WorkspaceDependency, current_time
from app.api.errors import error_responses
from app.contracts.export import ExportInfo
from app.export.service import export_run
from app.runs.contexts import load_export_context
from app.runs.queries import ExportFileKind, find_export_file, list_run_exports

router = APIRouter(prefix="/runs", tags=["exports"], responses=error_responses(403, 500, 503))

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# The OpenAPI entry of a file download
XLSX_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {"content": {XLSX_MEDIA_TYPE: {}}, "description": "The Excel file"}
}


@router.post(
    "/{run_id}/exports",
    summary="Export a run",
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(404, 409, 422),
)
def create_export(user: CurrentUser, workspace: WorkspaceDependency, run_id: str) -> ExportInfo:
    """Re-check if changes are pending, then write the loader and the audit file.

    An unverified run gives a draft export.
    """
    context = load_export_context(workspace, run_id)
    folder = workspace.run_store.open_run(run_id)
    return export_run(workspace.database, context, folder, run_id, user.name, current_time())


@router.get("/{run_id}/exports", summary="List exports", responses=error_responses(404, 422))
def list_exports(
    user: CurrentUser, workspace: WorkspaceDependency, run_id: str
) -> list[ExportInfo]:
    """Return the run's exports in number order."""
    return list_run_exports(workspace.database, run_id)


def send_export_file(
    workspace: WorkspaceDependency, run_id: str, export_id: str, kind: ExportFileKind
) -> FileResponse:
    """Return an export file as a download with its file name."""
    path = find_export_file(workspace, run_id, export_id, kind)
    return FileResponse(path, media_type=XLSX_MEDIA_TYPE, filename=path.name)


@router.get(
    "/{run_id}/exports/{export_id}/loader",
    summary="Download the loader",
    response_class=FileResponse,
    responses={**XLSX_RESPONSE, **error_responses(404, 422)},
)
def download_loader(
    user: CurrentUser, workspace: WorkspaceDependency, run_id: str, export_id: str
) -> FileResponse:
    """Download the export's DFD loader workbook."""
    return send_export_file(workspace, run_id, export_id, "loader")


@router.get(
    "/{run_id}/exports/{export_id}/audit",
    summary="Download the audit workbook",
    response_class=FileResponse,
    responses={**XLSX_RESPONSE, **error_responses(404, 422)},
)
def download_audit(
    user: CurrentUser, workspace: WorkspaceDependency, run_id: str, export_id: str
) -> FileResponse:
    """Download the export's audit workbook."""
    return send_export_file(workspace, run_id, export_id, "audit")
