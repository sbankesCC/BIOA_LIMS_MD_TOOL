"""LLM trace record (CONTRACTS §10): one per LLM call; prompt and response live only in files."""

from datetime import datetime
from typing import Literal

from app.contracts.base import ContractModel

LlmNode = Literal["extraction", "extraction_verification", "duplicate_judge"]
TraceStatus = Literal["ok", "retry", "error", "schema_violation"]


class LlmTrace(ContractModel):
    """Metadata of one LLM call: IDs, versions, timing, token counts and outcome."""

    trace_id: str
    run_id: str
    node: LlmNode
    attempt: int
    provider: str
    model: str
    prompt_template: str
    prompt_version: str
    config_versions: dict[str, str]
    started_at: datetime
    duration_ms: int
    input_tokens: int
    output_tokens: int
    cost_estimate: float | None = None
    status: TraceStatus
    error_message: str | None = None
    request_file: str
    response_file: str
