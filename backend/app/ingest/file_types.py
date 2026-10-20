"""Accepted upload types (ARCHITECTURE §9a): only `.docx`, `.pdf` and `.xlsx`, never macro files.

Used by the run store before saving an upload, and by ingest to pick a reader.
"""

from pathlib import PurePath
from typing import Literal

FileType = Literal["docx", "pdf", "xlsx"]

# Extension (lower case) to file type; anything else is refused, including `.xls` and `.xlsm`
ACCEPTED_EXTENSIONS: dict[str, FileType] = {
    ".docx": "docx",
    ".pdf": "pdf",
    ".xlsx": "xlsx",
}


class RejectedFileError(Exception):
    """Raised when an upload's name or type is not accepted; the message says what to do."""


def read_file_type(file_name: str) -> FileType:
    """Return the file type of an upload name, or raise RejectedFileError for any other type."""
    check_plain_file_name(file_name)
    extension = PurePath(file_name).suffix.lower()
    file_type = ACCEPTED_EXTENSIONS.get(extension)
    if file_type is None:
        accepted = ", ".join(sorted(ACCEPTED_EXTENSIONS))
        raise RejectedFileError(
            f"'{file_name}' is not an accepted file type. Upload only {accepted} files."
        )
    return file_type


def check_plain_file_name(file_name: str) -> None:
    """Refuse empty names and names with folder parts, so an upload stays inside its folder."""
    is_plain = (
        file_name.strip() != ""
        and "/" not in file_name
        and "\\" not in file_name
        and file_name not in {".", ".."}
    )
    if not is_plain:
        raise RejectedFileError(
            f"'{file_name}' is not a valid file name. Rename the file and upload it again."
        )
