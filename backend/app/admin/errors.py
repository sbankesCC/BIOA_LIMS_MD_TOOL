"""Admin errors: each has a code (for the API error shape) and a plain message.

The API (M9) maps the codes to status codes: VERSION_NOT_FOUND 404; UPLOAD_STALE and
VERSION_ALREADY_CURRENT 409.
"""

from typing import Literal

AdminErrorCode = Literal["VERSION_NOT_FOUND", "UPLOAD_STALE", "VERSION_ALREADY_CURRENT"]


class AdminError(Exception):
    """An admin request that cannot be done; the message says what to do next."""

    def __init__(self, code: AdminErrorCode, message: str) -> None:
        """Keep the code for the API and the message for the user."""
        self.code: AdminErrorCode = code
        self.message = message
        super().__init__(message)
