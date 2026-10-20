"""One error shape for every API error (CONTRACTS §13), with plain messages that say what to do.

Service errors carry a code; this module maps each code to its status and turns every error
(service, setting, validation, unknown route, unexpected) into `{"error": {...}}`.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import JsonValue
from starlette.exceptions import HTTPException

from app.admin.errors import AdminError
from app.contracts.api import ErrorBody, ErrorResponse
from app.ingest.file_types import RejectedFileError
from app.llm.provider import LLMProviderError
from app.review.errors import ReviewError
from app.runs.errors import RunRequestError
from app.settings import MissingSettingError
from app.storage.review_db import ReviewDatabaseError, RunNotFoundError
from app.storage.run_store import RunStoreError

# Status of every error code a service or the API raises
STATUS_BY_CODE: dict[str, int] = {
    "CHANGE_INVALID": 400,
    "BULK_NOT_POSSIBLE": 400,
    "NO_FILES": 400,
    "FILE_REJECTED": 400,
    "FORBIDDEN": 403,
    "RUN_NOT_FOUND": 404,
    "RECORD_NOT_FOUND": 404,
    "ISSUE_NOT_FOUND": 404,
    "CHUNK_NOT_FOUND": 404,
    "EXPORT_NOT_FOUND": 404,
    "VERSION_NOT_FOUND": 404,
    "BULK_ACCEPT_NOT_ALLOWED": 409,
    "RUN_NOT_IN_REVIEW": 409,
    "RUN_NOT_FAILED": 409,
    "UPLOAD_STALE": 409,
    "VERSION_ALREADY_CURRENT": 409,
    "FILE_TOO_LARGE": 413,
    "TOO_MANY_FILES": 413,
    "VALIDATION_FAILED": 422,
    "UNEXPECTED_ERROR": 500,
    "STORAGE_ERROR": 500,
    "SETTING_MISSING": 503,
    "SETTING_INVALID": 503,
}

# Plain descriptions of each status, used in the OpenAPI schema
STATUS_DESCRIPTIONS: dict[int, str] = {
    400: "Invalid request",
    403: "The signed-in user does not have the role this needs",
    404: "Not found",
    409: "Conflict with the run's status or the current version",
    413: "Upload too large",
    422: "The request did not pass validation",
    500: "Unexpected error",
    503: "A setting the feature needs is blank or wrong",
}

UNEXPECTED_MESSAGE = (
    "Something went wrong on the server. Try again; if it fails again, contact support."
)
VALIDATION_MESSAGE = (
    "The request is not valid. Check the fields listed in details and send it again."
)


class ApiError(Exception):
    """An error raised by the API layer itself (e.g. a wrong role)."""

    def __init__(
        self, code: str, message: str, details: dict[str, JsonValue] | None = None
    ) -> None:
        """Keep the code, message and details for the error response."""
        self.code = code
        self.message = message
        self.details: dict[str, JsonValue] = details or {}
        super().__init__(message)


def make_error_response(
    code: str, message: str, details: dict[str, JsonValue] | None = None, status: int | None = None
) -> JSONResponse:
    """Return the error shape with the code's status (or the given one)."""
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details or {}))
    return JSONResponse(
        status_code=status or STATUS_BY_CODE.get(code, 500), content=body.model_dump(mode="json")
    )


def error_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """Return OpenAPI response entries with the error shape for the given statuses."""
    return {
        status: {"model": ErrorResponse, "description": STATUS_DESCRIPTIONS[status]}
        for status in statuses
    }


# Every error class the API turns into the error shape; Exception catches the unexpected
HANDLED_ERRORS: tuple[type[Exception], ...] = (
    ApiError,
    RunRequestError,
    ReviewError,
    AdminError,
    MissingSettingError,
    LLMProviderError,
    RejectedFileError,
    ReviewDatabaseError,
    RunStoreError,
    RequestValidationError,
    HTTPException,
    Exception,
)


def register_error_handlers(app: FastAPI) -> None:
    """Send every handled error class through `handle_error`."""
    for error_class in HANDLED_ERRORS:
        app.add_exception_handler(error_class, handle_error)


def handle_error(request: Request, error: Exception) -> JSONResponse:
    """Return the error shape for any error raised while answering a request."""
    return to_error_response(error)


def to_error_response(error: Exception) -> JSONResponse:
    """Map an error to its code, status and plain message."""
    # Service and API errors carry their own code
    if isinstance(error, ApiError | RunRequestError):
        return make_error_response(error.code, error.message, error.details)
    if isinstance(error, ReviewError | AdminError):
        return make_error_response(error.code, error.message)
    # Settings: the message names the setting to fill in
    if isinstance(error, MissingSettingError):
        return make_error_response("SETTING_MISSING", str(error), {"setting": error.name})
    if isinstance(error, LLMProviderError):
        return make_error_response("SETTING_INVALID", str(error))
    if isinstance(error, RejectedFileError):
        return make_error_response("FILE_REJECTED", str(error))
    # A run not in the review database; other storage errors are unexpected
    if isinstance(error, RunNotFoundError):
        return make_error_response("RUN_NOT_FOUND", str(error))
    if isinstance(error, ReviewDatabaseError | RunStoreError):
        return make_error_response("STORAGE_ERROR", str(error))
    if isinstance(error, RequestValidationError):
        return make_validation_response(error)
    if isinstance(error, HTTPException):
        return make_http_response(error)
    return make_error_response("UNEXPECTED_ERROR", UNEXPECTED_MESSAGE)


def make_validation_response(error: RequestValidationError) -> JSONResponse:
    """Return a 422 listing where each problem is and what is wrong (never the sent values)."""
    problems: list[JsonValue] = [
        {
            "location": [str(part) for part in problem["loc"]],
            "message": str(problem["msg"]),
            "type": str(problem["type"]),
        }
        for problem in error.errors()
    ]
    return make_error_response("VALIDATION_FAILED", VALIDATION_MESSAGE, {"problems": problems})


def make_http_response(error: HTTPException) -> JSONResponse:
    """Return the error shape for routing errors (unknown address, wrong method)."""
    if error.status_code == 404:
        return make_error_response(
            "NOT_FOUND", "This address does not exist. Check the URL.", None, 404
        )
    if error.status_code == 405:
        message = "This address does not accept this method. Check the API description."
        return make_error_response("METHOD_NOT_ALLOWED", message, None, 405)
    return make_error_response(
        f"HTTP_{error.status_code}", str(error.detail), None, error.status_code
    )
