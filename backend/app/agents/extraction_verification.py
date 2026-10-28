"""Extraction verification agent (ARCHITECTURE §4.6, LLM part): reports problems, never values.

It sees the same chunks as extraction, the records with their record IDs, the excluded items,
and the code citation check results. A response that does not fit the schema is retried once;
a second failure (or a failed call) fails the step with EXTRACTION_FAILED.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.agents.common import AgentError, call_with_one_retry, make_request, parse_response
from app.agents.extraction import EXTRACTION_FAILED
from app.config.field_rules import FieldRules
from app.config.prompts import PromptTemplate
from app.contracts.chunk import Chunk
from app.contracts.extraction import ExcludedItem
from app.contracts.record import StoredRecord
from app.contracts.verification import VerificationOutput
from app.llm.client import LLMCallError, LLMResponse
from app.llm.prompt_builder import (
    build_prompt_parts,
    format_citation_results,
    format_excluded_items,
    format_records,
)
from app.llm.tracing import TracedCaller
from app.llm_schema import build_verification_schema

NODE = "extraction_verification"


@dataclass(frozen=True)
class VerificationTask:
    """What one verification call needs: chunks, records (citation-checked) and excluded items."""

    run_id: str
    chunks: Sequence[Chunk]
    records: Sequence[StoredRecord]
    excluded_items: Sequence[ExcludedItem]
    field_rules: FieldRules
    template: PromptTemplate


def run_verification(caller: TracedCaller, task: VerificationTask) -> VerificationOutput:
    """Run the verification call; raise AgentError (EXTRACTION_FAILED) if it cannot finish."""
    values = {
        "citation_results": format_citation_results(task.records),
        "records": format_records(task.records),
        "excluded_items": format_excluded_items(task.excluded_items),
    }
    parts = build_prompt_parts(task.template, values, task.chunks)
    schema = build_verification_schema(task.field_rules)
    request = make_request(task.run_id, NODE, task.template, parts, schema)
    try:
        result = call_with_one_retry(caller, request, check_verification_response)
    except LLMCallError as error:
        raise AgentError(EXTRACTION_FAILED, str(error)) from error
    if result.problem is not None:
        raise AgentError(EXTRACTION_FAILED, "The verification response broke the schema twice.")
    return VerificationOutput.model_validate_json(result.response.text)


def check_verification_response(response: LLMResponse) -> str | None:
    """Return a summary of the schema problems in a response, or None if it fits."""
    parsed = parse_response(response.text, VerificationOutput)
    return parsed if isinstance(parsed, str) else None
