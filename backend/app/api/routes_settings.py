"""Settings routes (CONTRACTS §13): the upload limits the Start screen shows.

Only the upload limits are exposed; no other setting value ever leaves the app.
"""

from fastapi import APIRouter

from app.api.auth import CurrentUser
from app.api.dependencies import Resources
from app.api.errors import error_responses
from app.contracts.api import UploadLimits

router = APIRouter(prefix="/settings", tags=["settings"], responses=error_responses(403, 500, 503))


@router.get("/upload-limits", summary="Get the upload limits")
def get_upload_limits(user: CurrentUser, resources: Resources) -> UploadLimits:
    """Return MAX_FILE_SIZE_MB and MAX_FILES_PER_RUN; null means the limit is not set."""
    settings = resources.settings
    return UploadLimits(
        max_file_size_mb=settings.max_file_size_mb,
        max_files_per_run=settings.max_files_per_run,
    )
