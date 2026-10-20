"""Version history for the admin screens, and the download name of a lookup list workbook.

The history lists every upload plus the version new runs use.
"""

from pathlib import PurePath

from app.admin import reference_data
from app.admin.lookup_lists import LookupListAdmin
from app.admin.reference_data import ReferenceDataAdmin
from app.config.lookup_lists import FILE_NAME
from app.contracts.api import DataVersionList


def list_lookup_versions(admin: LookupListAdmin) -> DataVersionList:
    """Return the lookup list uploads and the current version (the seed's name if none applied)."""
    return DataVersionList(
        current_version=admin.find_current_lookup_lists().version,
        versions=admin.list_versions(),
    )


def list_reference_versions(admin: ReferenceDataAdmin) -> DataVersionList:
    """Return the reference data uploads and the current version (None if none applied)."""
    current = admin.database.read_current_data_version(reference_data.KIND)
    return DataVersionList(
        current_version=current.version_id if current is not None else None,
        versions=admin.list_versions(),
    )


def make_lookup_download_name(admin: LookupListAdmin, version_id: str | None) -> str:
    """Return the download file name of a lookup list workbook, e.g. `lookup_lists v2.xlsx`."""
    version = version_id or admin.find_current_lookup_lists().version
    name = PurePath(FILE_NAME)
    return f"{name.stem} {version}{name.suffix}"
