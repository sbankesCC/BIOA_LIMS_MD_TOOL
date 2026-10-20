"""Admin routes (CONTRACTS §13): lookup list and reference data versions. Admin role only.

Thin: each route calls the lookup list or reference data admin service.
"""

from typing import Annotated

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response

from app.admin.history import (
    describe_data_version,
    describe_lookup_upload,
    describe_reference_upload,
    list_lookup_versions,
    list_reference_versions,
    make_lookup_download_name,
)
from app.api.auth import CurrentAdmin
from app.api.dependencies import WorkspaceDependency, current_time
from app.api.errors import error_responses
from app.api.routes_exports import XLSX_MEDIA_TYPE, XLSX_RESPONSE
from app.contracts.api import (
    DataVersionInfo,
    DataVersionList,
    LookupUploadResponse,
    ReferenceUploadResponse,
)

router = APIRouter(prefix="/admin", tags=["admin"], responses=error_responses(403, 500, 503))

UploadedWorkbook = Annotated[UploadFile, File(description="The file to upload.")]


def make_download(content: bytes, file_name: str) -> Response:
    """Return an Excel file as a download with its file name."""
    disposition = f'attachment; filename="{file_name}"'
    return Response(
        content, media_type=XLSX_MEDIA_TYPE, headers={"Content-Disposition": disposition}
    )


# ----- Lookup lists -----


@router.get(
    "/lookup-lists/current",
    summary="Download the current lookup lists",
    response_class=Response,
    responses=XLSX_RESPONSE,
)
def download_current_lookup_lists(admin: CurrentAdmin, workspace: WorkspaceDependency) -> Response:
    """Download the current lookup list workbook, with its version in `_metadata`."""
    lookup_admin = workspace.lookup_admin()
    content = lookup_admin.download_workbook(admin.name, current_time())
    return make_download(content, make_lookup_download_name(lookup_admin, None))


@router.post("/lookup-lists", summary="Upload lookup lists", responses=error_responses(422))
def upload_lookup_lists(
    admin: CurrentAdmin, workspace: WorkspaceDependency, file: UploadedWorkbook
) -> LookupUploadResponse:
    """Check an edited workbook: report and changes; without problems it becomes pending."""
    result = workspace.lookup_admin().upload_workbook(
        file.filename or "", file.file.read(), admin.name, current_time()
    )
    return describe_lookup_upload(result)


@router.post(
    "/lookup-lists/{version_id}/apply",
    summary="Apply or restore a lookup list version",
    responses=error_responses(404, 409, 422),
)
def apply_lookup_lists(
    admin: CurrentAdmin, workspace: WorkspaceDependency, version_id: str
) -> DataVersionInfo:
    """Make a pending upload (by upload ID) current as the next vN, or restore an older version."""
    version = workspace.lookup_admin().apply_version(version_id, admin.name, current_time())
    return describe_data_version(version)


@router.get("/lookup-lists/versions", summary="List lookup list versions")
def list_lookup_list_versions(
    admin: CurrentAdmin, workspace: WorkspaceDependency
) -> DataVersionList:
    """Return every upload and the version new runs use."""
    return list_lookup_versions(workspace.lookup_admin())


@router.get(
    "/lookup-lists/versions/{version_id}/download",
    summary="Download a lookup list version",
    response_class=Response,
    responses={**XLSX_RESPONSE, **error_responses(404, 422)},
)
def download_lookup_list_version(
    admin: CurrentAdmin, workspace: WorkspaceDependency, version_id: str
) -> Response:
    """Download any version's workbook (the seed's name, a vN, or an upload ID)."""
    lookup_admin = workspace.lookup_admin()
    content = lookup_admin.download_workbook(admin.name, current_time(), version_id)
    return make_download(content, make_lookup_download_name(lookup_admin, version_id))


# ----- Reference data -----


@router.post("/reference-data", summary="Upload reference data", responses=error_responses(422))
def upload_reference_data(
    admin: CurrentAdmin, workspace: WorkspaceDependency, file: UploadedWorkbook
) -> ReferenceUploadResponse:
    """Check an export of existing Consumable Types; without problems it becomes pending."""
    result = workspace.reference_admin().upload(
        file.filename or "", file.file.read(), admin.name, current_time()
    )
    return describe_reference_upload(result)


@router.post(
    "/reference-data/{version_id}/apply",
    summary="Apply or restore a reference data version",
    responses=error_responses(404, 409, 422),
)
def apply_reference_data(
    admin: CurrentAdmin, workspace: WorkspaceDependency, version_id: str
) -> DataVersionInfo:
    """Make a pending upload (by upload ID) current as the next vN, or restore an older version."""
    version = workspace.reference_admin().apply_version(version_id, admin.name, current_time())
    return describe_data_version(version)


@router.get("/reference-data/versions", summary="List reference data versions")
def list_reference_data_versions(
    admin: CurrentAdmin, workspace: WorkspaceDependency
) -> DataVersionList:
    """Return every upload and the version new runs use."""
    return list_reference_versions(workspace.reference_admin())
