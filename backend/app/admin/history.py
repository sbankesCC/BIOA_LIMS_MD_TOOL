"""Version history for the admin screens, and the download name of a lookup list workbook.

The history lists every upload plus the version new runs use. What the API shows of an upload
has its uploaded file name, never its storage path.
"""

from pathlib import PurePath

from app.admin import reference_data
from app.admin.lookup_lists import LookupListAdmin, LookupUploadResult
from app.admin.reference_data import ReferenceDataAdmin, ReferenceUploadResult
from app.config.lookup_lists import FILE_NAME
from app.contracts.api import (
    DataVersionInfo,
    DataVersionList,
    LookupUploadResponse,
    ReferenceUploadResponse,
)
from app.storage.review_db import DataVersion

# The summary key that holds the name the file was uploaded with
FILE_NAME_KEY = "file_name"


def describe_data_version(version: DataVersion) -> DataVersionInfo:
    """Return what the API shows of an upload: its uploaded file name instead of its path."""
    uploaded_name = version.summary.get(FILE_NAME_KEY)
    # Every upload's summary names its file; the stored file's own name is the fallback
    file_name = uploaded_name if isinstance(uploaded_name, str) else PurePath(version.file_ref).name
    return DataVersionInfo(
        upload_id=version.upload_id,
        version_id=version.version_id,
        status=version.status,
        file_name=file_name,
        based_on_version=version.based_on_version,
        uploaded_by=version.uploaded_by,
        uploaded_at=version.uploaded_at,
        applied_by=version.applied_by,
        applied_at=version.applied_at,
        summary=version.summary,
    )


def describe_lookup_upload(result: LookupUploadResult) -> LookupUploadResponse:
    """Return a lookup list upload's report and its pending version, without storage paths."""
    version = describe_data_version(result.version) if result.version is not None else None
    return LookupUploadResponse(report=result.report, version=version)


def describe_reference_upload(result: ReferenceUploadResult) -> ReferenceUploadResponse:
    """Return a reference data upload's report and its pending version, without storage paths."""
    version = describe_data_version(result.version) if result.version is not None else None
    return ReferenceUploadResponse(report=result.report, version=version)


def list_lookup_versions(admin: LookupListAdmin) -> DataVersionList:
    """Return the lookup list uploads and the current version (the seed's name if none applied)."""
    return DataVersionList(
        current_version=admin.find_current_lookup_lists().version,
        versions=[describe_data_version(version) for version in admin.list_versions()],
    )


def list_reference_versions(admin: ReferenceDataAdmin) -> DataVersionList:
    """Return the reference data uploads and the current version (None if none applied)."""
    current = admin.database.read_current_data_version(reference_data.KIND)
    return DataVersionList(
        current_version=current.version_id if current is not None else None,
        versions=[describe_data_version(version) for version in admin.list_versions()],
    )


def make_lookup_download_name(admin: LookupListAdmin, version_id: str | None) -> str:
    """Return the download file name of a lookup list workbook, e.g. `lookup_lists v2.xlsx`."""
    version = version_id or admin.find_current_lookup_lists().version
    name = PurePath(FILE_NAME)
    return f"{name.stem} {version}{name.suffix}"
