"""LLM call tracing and retries (CONTRACTS §10): every call is written to the run store.

Per call: `llm/llm_0001.json` (the trace record), `llm_0001_request.json` and
`llm_0001_response.json`. Timeouts and rate limits are retried up to LLM_RETRIES times; each
try gets its own trace. Log lines hold IDs, counts and durations only.
"""

import json
import re
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from app.contracts.trace import LlmTrace, TraceStatus
from app.ids import IdCounter
from app.llm.client import LLMCallError, LLMClient, LLMRequest, LLMResponse
from app.logging_setup import log_event
from app.storage.run_store import RunFolder, write_json

TRACE_PREFIX = "llm_"
TRACE_FILE_PATTERN = re.compile(r"^(?P<trace_id>llm_\d+)\.json$")
TRACE_SUFFIX = ".json"
REQUEST_SUFFIX = "_request.json"
RESPONSE_SUFFIX = "_response.json"

# Message of a response that stopped at the output token limit
TRUNCATED_MESSAGE = "The response stopped at the output token limit."

# Checks a response; returns a plain problem summary (IDs and keys only), or None when fine
ResponseCheck = Callable[[LLMResponse], str | None]


class TracedResult(BaseModel):
    """One finished call: the response, its trace ID, and the problem the check found, if any."""

    response: LLMResponse
    trace_id: str
    problem: str | None = None


class TracedCaller:
    """Calls an LLM client for one run, retrying transient failures and tracing every try."""

    def __init__(
        self,
        client: LLMClient,
        folder: RunFolder,
        config_versions: Mapping[str, str],
        retries: int,
    ) -> None:
        """Set up tracing into the run's `llm/` folder; `retries` comes from LLM_RETRIES."""
        self.client = client
        self.folder = folder
        self.config_versions = dict(config_versions)
        self.retries = retries
        self.trace_ids = IdCounter(TRACE_PREFIX, (t.trace_id for t in read_traces(folder)))

    def call(self, request: LLMRequest, attempt: int, check: ResponseCheck) -> TracedResult:
        """Call the LLM, retrying retryable errors; raise LLMCallError once the tries run out."""
        tries_left = self.retries
        while True:
            try:
                return self.call_once(request, attempt, check, is_last_try=tries_left == 0)
            except LLMCallError as error:
                if not error.is_retryable or tries_left == 0:
                    raise
                tries_left -= 1
                log_event(
                    "retry_scheduled",
                    run_id=request.run_id,
                    node=request.node,
                    attempt=attempt,
                    details={"tries_left": tries_left},
                )

    def call_once(
        self, request: LLMRequest, attempt: int, check: ResponseCheck, is_last_try: bool
    ) -> TracedResult:
        """Make one try: write the request, call, write the response and the trace record."""
        trace_id = self.trace_ids.next_id()
        model = self.client.model_for(request.node)
        write_json(self.file_path(trace_id, REQUEST_SUFFIX), build_request_file(request, model))
        outcome = TraceOutcome(model=model, started_at=datetime.now(UTC), status="ok")
        start = time.perf_counter()
        try:
            response = self.client.complete(request)
        except LLMCallError as error:
            # A failed try is traced too; "retry" when another try follows
            outcome.status = "retry" if error.is_retryable and not is_last_try else "error"
            outcome.error_message = str(error)
            outcome.duration_ms = elapsed_ms(start)
            write_json(self.file_path(trace_id, RESPONSE_SUFFIX), {"error": str(error)})
            self.finish(request, attempt, trace_id, outcome)
            raise
        outcome.duration_ms = elapsed_ms(start)
        # A cut-off response or one that fails the caller's check is a schema violation
        problem = TRUNCATED_MESSAGE if response.is_truncated else check(response)
        write_json(self.file_path(trace_id, RESPONSE_SUFFIX), response.model_dump(mode="json"))
        outcome.model = response.model
        outcome.status = "ok" if problem is None else "schema_violation"
        outcome.error_message = problem
        outcome.input_tokens = response.input_tokens
        outcome.output_tokens = response.output_tokens
        self.finish(request, attempt, trace_id, outcome)
        return TracedResult(response=response, trace_id=trace_id, problem=problem)

    def finish(
        self, request: LLMRequest, attempt: int, trace_id: str, outcome: "TraceOutcome"
    ) -> None:
        """Write the trace record and the `llm_call_finished` log line."""
        trace = LlmTrace(
            trace_id=trace_id,
            run_id=request.run_id,
            node=request.node,
            attempt=attempt,
            provider=self.client.provider,
            model=outcome.model,
            prompt_template=request.prompt_template,
            prompt_version=request.prompt_version,
            config_versions=self.config_versions,
            started_at=outcome.started_at,
            duration_ms=outcome.duration_ms,
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
            status=outcome.status,
            error_message=outcome.error_message,
            request_file=self.folder.make_ref(self.file_path(trace_id, REQUEST_SUFFIX)),
            response_file=self.folder.make_ref(self.file_path(trace_id, RESPONSE_SUFFIX)),
        )
        write_json(self.file_path(trace_id, TRACE_SUFFIX), trace.model_dump(mode="json"))
        log_event(
            "llm_call_finished",
            level="INFO" if outcome.status == "ok" else "WARNING",
            run_id=request.run_id,
            node=request.node,
            attempt=attempt,
            duration_ms=outcome.duration_ms,
            details={"input_tokens": outcome.input_tokens, "output_tokens": outcome.output_tokens},
        )

    def file_path(self, trace_id: str, suffix: str) -> Path:
        """Return the path of one of a call's files (trace record, request or response)."""
        return self.folder.llm_dir / f"{trace_id}{suffix}"


class TraceOutcome(BaseModel):
    """What one try gave, gathered while it runs, for its trace record."""

    model: str
    started_at: datetime
    status: TraceStatus
    duration_ms: int = 0
    error_message: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0


def elapsed_ms(start: float) -> int:
    """Return the milliseconds since a `time.perf_counter()` reading."""
    return round((time.perf_counter() - start) * 1000)


def build_request_file(request: LLMRequest, model: str) -> dict[str, object]:
    """Return what the request file holds: the whole prompt, schema and model (images by ref)."""
    return {"model": model, **request.model_dump(mode="json")}


def read_traces(folder: RunFolder) -> list[LlmTrace]:
    """Return the run's trace records in trace ID order."""
    if not folder.llm_dir.is_dir():
        return []
    paths = [path for path in folder.llm_dir.iterdir() if TRACE_FILE_PATTERN.match(path.name)]
    traces = [LlmTrace.model_validate(json.loads(path.read_bytes())) for path in paths]
    return sorted(traces, key=lambda trace: trace.trace_id)
