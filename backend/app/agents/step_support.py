"""Shared support for the model steps (Matching, Naming, plausibility review).

Each step is one constrained call that never fails the run. This module holds what they share:
the result cache (text by hash key), the call budget, and the hash that builds a cache key.
"""

import hashlib
import json
from typing import Protocol

from app.agents.common import call_with_one_retry
from app.llm.client import LLMCallError, LLMRequest
from app.llm.tracing import ResponseCheck, TracedCaller


class StepCache(Protocol):
    """Stores one model step's results as JSON text by cache key."""

    def get(self, key: str) -> str | None:
        """Return the cached text for a key, or None."""
        ...

    def put(self, key: str, output: str) -> None:
        """Store text under a key."""
        ...


class InMemoryStepCache:
    """A step cache that lives as long as the object (tests and evals)."""

    def __init__(self) -> None:
        """Start empty."""
        self.results: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        """Return the cached text for a key, or None."""
        return self.results.get(key)

    def put(self, key: str, output: str) -> None:
        """Store text under a key."""
        self.results[key] = output


class CallBudget:
    """Counts a step's real calls and says when its limit is reached (None: no limit)."""

    def __init__(self, limit: int | None) -> None:
        """Set the limit; a blank setting (None) means no limit."""
        self.limit = limit
        self.calls_made = 0

    def is_limit_reached(self) -> bool:
        """Return True when no more calls are allowed."""
        return self.limit is not None and self.calls_made >= self.limit

    def record_call(self) -> None:
        """Count one real call (cached answers are never counted)."""
        self.calls_made += 1


def make_step_cache_key(parts: dict[str, object]) -> str:
    """Return a stable hash of the parts that decide a result (values, versions, model)."""
    # Sorted JSON keeps the key the same whatever order the parts came in
    text = json.dumps(parts, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def call_model_step(
    caller: TracedCaller,
    request: LLMRequest,
    check: ResponseCheck,
    budget: CallBudget,
    model: str | None,
) -> str | None:
    """Make a step's one call and return the response text; None means the step is skipped.

    A blank model, a reached call limit, or a call that fails after its retry all skip the step.
    """
    if model is None or budget.is_limit_reached():
        return None
    budget.record_call()
    try:
        result = call_with_one_retry(caller, request, check)
    except LLMCallError:
        return None
    return None if result.problem is not None else result.response.text
