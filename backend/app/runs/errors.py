"""Run request errors: each has a code (for the API error shape) and a plain message.

The API maps the codes to status codes (`api/errors.py`): NO_FILES and FILE_REJECTED 400;
RECORD_NOT_FOUND, CHUNK_NOT_FOUND and EXPORT_NOT_FOUND 404; RUN_NOT_FAILED 409; FILE_TOO_LARGE
and TOO_MANY_FILES 413.
"""

from typing import Literal

from pydantic import JsonValue

RunErrorCode = Literal[
    "NO_FILES",
    "FILE_REJECTED",
    "FILE_TOO_LARGE",
    "TOO_MANY_FILES",
    "RECORD_NOT_FOUND",
    "CHUNK_NOT_FOUND",
    "EXPORT_NOT_FOUND",
    "RUN_NOT_FAILED",
]


class RunRequestError(Exception):
    """A run request that cannot be done; the message says what to do next."""

    def __init__(
        self, code: RunErrorCode, message: str, details: dict[str, JsonValue] | None = None
    ) -> None:
        """Keep the code and details for the API and the message for the user."""
        self.code: RunErrorCode = code
        self.message = message
        self.details: dict[str, JsonValue] = details or {}
        super().__init__(message)
