"""Duplicate judge interface, its result cache, and the per-pass call limit.

The judge (an LLM agent, built in M8) sits behind the `DuplicateJudge` protocol. Results are
cached by the record's identifying values, the reference data version and the prompt version,
so a re-check calls the judge again only when one of those changed (ARCHITECTURE §4.8).
"""

import hashlib
import json
from typing import Protocol

from pydantic import BaseModel

from app.contracts.judge import JudgeOutput
from app.contracts.reference import ReferenceType


class JudgeRequest(BaseModel):
    """What the judge sees: the record's identifying values and the shortlisted existing types."""

    record_id: str
    values: dict[str, str | None]
    candidates: list[ReferenceType]


class DuplicateJudge(Protocol):
    """Decides, per shortlisted candidate, whether a record is the same material."""

    def judge(self, request: JudgeRequest) -> JudgeOutput:
        """Return one judgment per candidate in the request."""
        ...


class JudgeCache(Protocol):
    """Stores judge results by cache key; the review database backs it in M6."""

    def get(self, key: str) -> JudgeOutput | None:
        """Return the cached result for a key, or None."""
        ...

    def put(self, key: str, output: JudgeOutput) -> None:
        """Store a result under a key."""
        ...


class InMemoryJudgeCache:
    """A judge cache that lives as long as the object (tests, and one validation pass)."""

    def __init__(self) -> None:
        """Start empty."""
        self.results: dict[str, JudgeOutput] = {}

    def get(self, key: str) -> JudgeOutput | None:
        """Return the cached result for a key, or None."""
        return self.results.get(key)

    def put(self, key: str, output: JudgeOutput) -> None:
        """Store a result under a key."""
        self.results[key] = output


def make_judge_cache_key(
    values: dict[str, str | None], reference_version: str, prompt_version: str
) -> str:
    """Return a stable hash of the identifying values and the two versions."""
    # Sorted JSON keeps the key the same whatever order the values came in
    key = json.dumps(
        {"values": values, "reference": reference_version, "prompt": prompt_version},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class JudgeRunner:
    """Calls the judge through the cache and stops calling once the call limit is reached."""

    def __init__(
        self,
        judge: DuplicateJudge,
        cache: JudgeCache,
        prompt_version: str,
        call_limit: int | None,
    ) -> None:
        """Set up the runner; a `call_limit` of None means no limit (blank setting)."""
        self.judge = judge
        self.cache = cache
        self.prompt_version = prompt_version
        self.call_limit = call_limit
        self.calls_made = 0

    def is_limit_reached(self) -> bool:
        """Return True when no more judge calls are allowed in this pass."""
        return self.call_limit is not None and self.calls_made >= self.call_limit

    def judge_record(self, request: JudgeRequest, reference_version: str) -> JudgeOutput | None:
        """Return the judge's result (cached when possible), or None if the limit stops it."""
        key = make_judge_cache_key(request.values, reference_version, self.prompt_version)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        # A cached result costs nothing; only real calls count against the limit
        if self.is_limit_reached():
            return None
        output = self.judge.judge(request)
        self.calls_made += 1
        self.cache.put(key, output)
        return output
