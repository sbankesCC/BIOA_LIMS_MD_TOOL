"""Run routes (CONTRACTS §13): list, start (upload), detail, rename and retry.

Thin: each route reads the request, calls the run service or a run query, and returns its model.
"""

from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile, status

from app.api.auth import CurrentUser
from app.api.dependencies import TaskRunnerDependency, WorkspaceDependency, current_time
from app.api.errors import error_responses
from app.contracts.api import RenameRunRequest, RunDetail, RunName, RunSummary, StartRunResponse
from app.runs import service
from app.runs.queries import describe_run, list_run_summaries

router = APIRouter(prefix="/runs", tags=["runs"], responses=error_responses(403, 500, 503))


def read_uploads(uploads: list[UploadFile]) -> list[service.UploadedFile]:
    """Read every uploaded file into memory with its name."""
    return [
        service.UploadedFile(file_name=upload.filename or "", content=upload.file.read())
        for upload in uploads
    ]


@router.get("", summary="List runs")
def list_runs(user: CurrentUser, workspace: WorkspaceDependency) -> list[RunSummary]:
    """Return every run, newest first: name, status, record and open issue counts, verified."""
    return list_run_summaries(workspace.database)


@router.post(
    "",
    summary="Start a run",
    status_code=status.HTTP_202_ACCEPTED,
    responses=error_responses(400, 413, 422),
)
def create_run(
    user: CurrentUser,
    workspace: WorkspaceDependency,
    runner: TaskRunnerDependency,
    files: Annotated[list[UploadFile], File(description="The documents (.docx, .pdf, .xlsx).")],
    name: Annotated[RunName, Form(description="The run name.")],
) -> StartRunResponse:
    """Store the uploaded files as a new run and process it in the background."""
    uploads = read_uploads(files)
    service.check_uploads(uploads, workspace.settings)
    run_id = service.start_run(workspace, runner, name, uploads, user.name, current_time())
    return StartRunResponse(run_id=run_id)


@router.get("/{run_id}", summary="Get a run", responses=error_responses(404, 422))
def get_run(user: CurrentUser, workspace: WorkspaceDependency, run_id: str) -> RunDetail:
    """Return the run's status, current step, verified label, documents, exports and run issues."""
    return describe_run(workspace, run_id)


@router.patch("/{run_id}", summary="Rename a run", responses=error_responses(404, 422))
def rename_run(
    user: CurrentUser, workspace: WorkspaceDependency, run_id: str, body: RenameRunRequest
) -> RunDetail:
    """Give the run a new name; return the updated run."""
    service.rename_run(workspace.database, run_id, body.name)
    return describe_run(workspace, run_id)


@router.post(
    "/{run_id}/retry",
    summary="Retry a failed run",
    status_code=status.HTTP_202_ACCEPTED,
    responses=error_responses(404, 409, 422),
)
def retry_run(
    user: CurrentUser, workspace: WorkspaceDependency, runner: TaskRunnerDependency, run_id: str
) -> StartRunResponse:
    """Start a new run from a failed run's uploaded files; the failed run is not changed."""
    new_run_id = service.retry_run(workspace, runner, run_id, user.name, current_time())
    return StartRunResponse(run_id=new_run_id, retry_of=run_id)
