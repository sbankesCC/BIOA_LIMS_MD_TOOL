"""Shared helpers for admin data versions (lookup lists and reference data).

Uploads get an upload ID (`upl_0001`) and are stored under STORAGE_DIR; the first apply gives
the next `vN`. Version rows live in the review database (`DataVersion`).
"""

import re
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from app.admin.errors import AdminError
from app.contracts.run import AuditEvent
from app.ids import IdCounter
from app.storage.review_db import DataVersion, DataVersionKind, ReviewDatabase
from app.storage.run_store import resolve_inside

UPLOAD_PREFIX = "upl_"

# Applied versions are numbered v1, v2, ...; other names (such as the seed's) are not counted
VERSION_PATTERN = re.compile(r"v(\d+)")


class AppliedVersion(BaseModel):
    """The version made current, and whether it was a restore of an older one."""

    version: DataVersion
    is_restore: bool


def next_upload_id(versions: Sequence[DataVersion]) -> str:
    """Return the next unused upload ID (`upl_0001`, ...)."""
    return IdCounter(UPLOAD_PREFIX, [version.upload_id for version in versions]).next_id()


def next_version_id(versions: Sequence[DataVersion]) -> str:
    """Return the next version name: one more than the highest `vN` so far (`v1` at first)."""
    numbers = [
        int(match.group(1))
        for version in versions
        if version.version_id is not None
        and (match := VERSION_PATTERN.fullmatch(version.version_id)) is not None
    ]
    return f"v{max(numbers, default=0) + 1}"


def find_version(database: ReviewDatabase, kind: DataVersionKind, name: str) -> DataVersion:
    """Return the upload with this upload ID or version ID; raise AdminError if there is none."""
    for version in database.list_data_versions(kind):
        if name in (version.upload_id, version.version_id):
            return version
    raise AdminError(
        "VERSION_NOT_FOUND", f"Version {name} was not found. Check the version history."
    )


def apply_version(
    database: ReviewDatabase, kind: DataVersionKind, version: DataVersion, user: str, at: datetime
) -> AppliedVersion:
    """Make a pending upload current as the next `vN`, or restore a superseded version."""
    if version.status == "current":
        raise AdminError(
            "VERSION_ALREADY_CURRENT",
            f"Version {version.version_id} is already the current version. Nothing to apply.",
        )
    # A superseded version keeps its name when restored; a pending one gets the next name
    is_restore = version.version_id is not None
    version_id = version.version_id or next_version_id(database.list_data_versions(kind))
    applied = database.make_data_version_current(kind, version.upload_id, version_id, user, at)
    return AppliedVersion(version=applied, is_restore=is_restore)


def resolve_file_ref(storage_dir: Path, ref: str) -> Path:
    """Turn a stored file reference into a path inside STORAGE_DIR."""
    return resolve_inside(storage_dir, ref)


def make_file_ref(storage_dir: Path, path: Path) -> str:
    """Return a file's reference: its path relative to STORAGE_DIR, with forward slashes."""
    return path.relative_to(storage_dir).as_posix()


def make_admin_event(
    event: str, user: str, at: datetime, **details: str | int | None
) -> AuditEvent:
    """Build an admin event (no run) with plain details."""
    return AuditEvent(event=event, run_id=None, by=user, at=at, details=dict(details))
