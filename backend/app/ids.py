"""Prefixed IDs (CONTRACTS §4a): numbered IDs such as `rec_0001`, and stable issue IDs.

Record IDs come from code, never from the LLM. An issue ID is a hash of the issue's key, so a
validation re-run gives the same ID for the same problem.
"""

import hashlib
import json
from collections.abc import Iterable

RECORD_PREFIX = "rec_"
ISSUE_PREFIX = "iss_"

# Numbered IDs are zero-padded to this many digits (rec_0001); larger numbers just grow
NUMBER_WIDTH = 4

# Hex characters of the SHA-256 key hash kept in an issue ID (48 bits)
ISSUE_HASH_LENGTH = 12


class IdCounter:
    """Hands out numbered IDs with one prefix, continuing after the highest existing one."""

    def __init__(self, prefix: str, existing_ids: Iterable[str] = ()) -> None:
        """Start after the highest number among `existing_ids`, so no ID is ever reused."""
        self.prefix = prefix
        numbers = [read_id_number(prefix, existing_id) for existing_id in existing_ids]
        self.last_number = max(numbers, default=0)

    def next_id(self) -> str:
        """Return the next unused ID."""
        self.last_number += 1
        return format_numbered_id(self.prefix, self.last_number)


def make_record_id_counter(existing_ids: Iterable[str] = ()) -> IdCounter:
    """Return a counter for record IDs (`rec_0001`, ...) that skips the run's existing IDs."""
    return IdCounter(RECORD_PREFIX, existing_ids)


def format_numbered_id(prefix: str, number: int) -> str:
    """Format a numbered ID, e.g. `rec_` and 7 give `rec_0007`."""
    return f"{prefix}{number:0{NUMBER_WIDTH}d}"


def read_id_number(prefix: str, numbered_id: str) -> int:
    """Return the number in a numbered ID; raise ValueError if it is not `prefix` + digits."""
    digits = numbered_id.removeprefix(prefix)
    if not numbered_id.startswith(prefix) or not digits.isdigit():
        raise ValueError(f"'{numbered_id}' is not a {prefix}... ID. Check where this ID came from.")
    return int(digits)


def make_issue_id(code: str, record_id: str | None, field: str | None, value: str | None) -> str:
    """Return `iss_` + a short hash of (code, record_id, field, value); same key, same ID."""
    # JSON keeps null and empty text apart and needs no separator that a value could contain
    key = json.dumps([code, record_id, field, value], ensure_ascii=False)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return f"{ISSUE_PREFIX}{digest[:ISSUE_HASH_LENGTH]}"
