"""Review errors: each has a code (for the API error shape) and a plain message.

The API maps the codes to status codes (`api/errors.py`): CHANGE_INVALID and BULK_NOT_POSSIBLE
400; ISSUE_NOT_FOUND 404; BULK_ACCEPT_NOT_ALLOWED and RUN_NOT_IN_REVIEW 409.
"""

from typing import Literal

ReviewErrorCode = Literal[
    "CHANGE_INVALID",
    "BULK_ACCEPT_NOT_ALLOWED",
    "BULK_NOT_POSSIBLE",
    "ISSUE_NOT_FOUND",
    "RUN_NOT_IN_REVIEW",
]


class ReviewError(Exception):
    """A review request that cannot be done; the message says what to do next."""

    def __init__(self, code: ReviewErrorCode, message: str) -> None:
        """Keep the code for the API and the message for the user."""
        self.code: ReviewErrorCode = code
        self.message = message
        super().__init__(message)


class ChangeRejectedError(ReviewError):
    """A change that breaks a rule of CONTRACTS §6; nothing in the request was saved."""

    def __init__(self, message: str, code: ReviewErrorCode = "CHANGE_INVALID") -> None:
        """Build the error; the default code is CHANGE_INVALID."""
        super().__init__(code, message)


class RunNotInReviewError(ReviewError):
    """The run is not in review (still processing, or failed), so it cannot be changed."""

    def __init__(self, run_id: str) -> None:
        """Build a plain message naming the run."""
        super().__init__(
            "RUN_NOT_IN_REVIEW",
            f"Run {run_id} is not in review yet. Wait until it reaches review.",
        )
