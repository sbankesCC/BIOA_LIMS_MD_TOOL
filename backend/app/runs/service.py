"""Run service: checks uploads, starts, retries and renames runs.

A new run is stored, then processed in the background; a retry starts from a failed run's uploads.

A run captures its config versions, lookup lists, reference data and models when it starts.
"""

import re
from collections.abc import Sequence
from datetime import datetime
from functools import partial
from pathlib import Path

from pydantic import BaseModel

from app.graph.build import make_run_info, run_processing
from app.graph.context import ProcessingContext
from app.ids import IdCounter
from app.ingest.file_types import read_file_type
from app.runs.background import TaskRunner
from app.runs.contexts import make_processing_context
from app.runs.errors import RunRequestError
from app.runs.workspace import Workspace
from app.settings import Settings
from app.storage.review_db import ReviewDatabase

# Run IDs are numbered: run_0001, run_0002, ...; other names (such as eval runs) are not counted
RUN_PREFIX = "run_"
NUMBERED_RUN_ID = re.compile(r"run_\d+")

BYTES_PER_MB = 1024 * 1024


class UploadedFile(BaseModel):
    """One uploaded file: its name and contents."""

    file_name: str
    content: bytes


# ----- Upload checks -----


def check_uploads(files: Sequence[UploadedFile], settings: Settings) -> None:
    """Refuse an upload with no files, a refused type, or over a limit that is set."""
    if not files:
        raise RunRequestError("NO_FILES", "No files were uploaded. Add at least one file.")
    # The type check raises RejectedFileError, which names the file and the accepted types
    for file in files:
        read_file_type(file.file_name)
    check_file_count(files, settings.max_files_per_run)
    check_file_sizes(files, settings.max_file_size_mb)


def check_file_count(files: Sequence[UploadedFile], limit: int | None) -> None:
    """Refuse more files than MAX_FILES_PER_RUN; blank means no limit."""
    if limit is not None and len(files) > limit:
        raise RunRequestError(
            "TOO_MANY_FILES",
            f"{len(files)} files were uploaded, but a run takes at most {limit}. "
            "Remove some files and start again.",
            {"file_count": len(files), "limit": limit},
        )


def check_file_sizes(files: Sequence[UploadedFile], limit_mb: int | None) -> None:
    """Refuse a file larger than MAX_FILE_SIZE_MB; blank means no limit."""
    if limit_mb is None:
        return
    for file in files:
        if len(file.content) > limit_mb * BYTES_PER_MB:
            raise RunRequestError(
                "FILE_TOO_LARGE",
                f"'{file.file_name}' is larger than {limit_mb} MB. Upload a smaller file.",
                {"file_name": file.file_name, "limit_mb": limit_mb},
            )


# ----- Start and retry -----


def start_run(
    workspace: Workspace,
    runner: TaskRunner,
    name: str,
    files: Sequence[UploadedFile],
    user: str,
    at: datetime,
    retry_of: str | None = None,
) -> str:
    """Store a new run with its files and queue its processing; return the run ID.

    Everything the processing needs is built first, so a missing setting stores nothing.
    """
    client = workspace.make_client()
    lookup_lists = workspace.lookup_admin().find_current_lookup_lists()
    reference = workspace.reference_admin().find_current_reference_data()
    context = make_processing_context(workspace, lookup_lists, reference, client)
    checkpoint_path = workspace.settings.require_path("CHECKPOINT_DB")
    # The run ID, its folder, its files and its row are made together under the database lock
    with workspace.database.transaction():
        run_id = next_run_id(workspace)
        run = make_run_info(
            run_id, name, user, at, workspace.bundle, lookup_lists, reference, client, retry_of
        )
        folder = workspace.run_store.create_run(run_id)
        for file in files:
            folder.save_upload(file.file_name, file.content)
        workspace.database.add_run(run)
    runner.submit(partial(process_run, context, run_id, checkpoint_path))
    return run_id


def process_run(context: ProcessingContext, run_id: str, checkpoint_path: Path) -> None:
    """Process a run in the background; a failure is already stored and logged by the graph."""
    try:
        run_processing(context, run_id, checkpoint_path)
    except Exception:
        # The run is marked failed with a log line; the worker goes on with the next run
        return


def retry_run(
    workspace: Workspace, runner: TaskRunner, run_id: str, user: str, at: datetime
) -> str:
    """Start a new run from a failed run's uploaded files, linked by `retry_of`.

    The failed run is not changed. Returns the new run's ID.
    """
    failed = workspace.database.read_run(run_id)
    if failed.status != "failed":
        raise RunRequestError(
            "RUN_NOT_FAILED",
            f"Run {run_id} has not failed, so it cannot be retried. Only failed runs can be "
            "retried.",
        )
    folder = workspace.run_store.open_run(run_id)
    files = [
        UploadedFile(
            file_name=document.file_name, content=folder.upload_path(document).read_bytes()
        )
        for document in folder.read_documents()
    ]
    return start_run(workspace, runner, failed.name, files, user, at, retry_of=run_id)


def next_run_id(workspace: Workspace) -> str:
    """Return the next run ID, after every run in the database and every run folder."""
    known_ids = [run.run_id for run in workspace.database.list_runs()]
    known_ids += workspace.run_store.list_run_ids()
    numbered = [run_id for run_id in known_ids if NUMBERED_RUN_ID.fullmatch(run_id)]
    return IdCounter(RUN_PREFIX, numbered).next_id()


# ----- Rename -----


def rename_run(database: ReviewDatabase, run_id: str, name: str) -> None:
    """Give a run a new name; raise RunNotFoundError if it is not stored."""
    database.update_run(run_id, name=name)
