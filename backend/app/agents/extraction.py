"""Extraction agent (ARCHITECTURE §4.5): one LLM call finds the records and copies their values.

Before calling, code estimates the input tokens; over MAX_INPUT_TOKENS the run fails with
DOCUMENT_SET_TOO_LARGE and no call is made. Each response is checked against the schema and the
status rules (CONTRACTS §2); a violation is retried once, then the step fails.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.agents.common import (
    AgentError,
    call_with_one_retry,
    make_request,
    parse_response,
    summarize_problems,
)
from app.config.field_rules import FieldRules
from app.config.prompts import PromptTemplate
from app.contracts.chunk import Chunk
from app.contracts.extraction import ExtractionOutput
from app.ids import RECORD_PREFIX
from app.llm.client import LLMCallError, LLMResponse, PromptPart
from app.llm.prompt_builder import build_field_section, build_prompt_parts
from app.llm.token_estimate import ImageSizeReader, estimate_parts_tokens
from app.llm.tracing import ResponseCheck, TracedCaller
from app.llm_schema import build_extraction_schema
from app.status_rules import find_status_violations

NODE = "extraction"

# Run issue codes the graph raises when extraction fails (defined in the issue catalogue)
EXTRACTION_FAILED = "EXTRACTION_FAILED"
DOCUMENT_SET_TOO_LARGE = "DOCUMENT_SET_TOO_LARGE"


@dataclass(frozen=True)
class ExtractionTask:
    """What one extraction call needs: the run's chunks, field rules, prompt and limits.

    On re-extraction, `reextraction_section` lists the problems and `allowed_record_ids` the
    existing records the response may return by their record_id.
    """

    run_id: str
    chunks: Sequence[Chunk]
    field_rules: FieldRules
    template: PromptTemplate
    max_input_tokens: int | None
    reextraction_section: str = ""
    allowed_record_ids: frozenset[str] = field(default_factory=frozenset[str])


def run_extraction(
    caller: TracedCaller, task: ExtractionTask, read_image_size: ImageSizeReader
) -> ExtractionOutput:
    """Run the extraction call; raise AgentError (EXTRACTION_FAILED or too large) on failure."""
    values = {
        "field_section": build_field_section(task.field_rules),
        "reextraction_section": task.reextraction_section,
    }
    parts = build_prompt_parts(task.template, values, task.chunks)
    schema = build_extraction_schema(task.field_rules)
    check_input_size(parts, schema, task.max_input_tokens, read_image_size)
    request = make_request(task.run_id, NODE, task.template, parts, schema)
    try:
        result = call_with_one_retry(caller, request, make_extraction_check(task))
    except LLMCallError as error:
        raise AgentError(EXTRACTION_FAILED, str(error)) from error
    # A response still cut off after the retry means the document set is too large
    if result.response.is_truncated:
        raise AgentError(DOCUMENT_SET_TOO_LARGE, "The extraction response was cut off.")
    if result.problem is not None:
        raise AgentError(EXTRACTION_FAILED, "The extraction response broke the rules twice.")
    return ExtractionOutput.model_validate_json(result.response.text)


def check_input_size(
    parts: Sequence[PromptPart],
    schema: dict[str, object],
    max_input_tokens: int | None,
    read_image_size: ImageSizeReader,
) -> None:
    """Raise DOCUMENT_SET_TOO_LARGE when the estimate is over the limit (blank: no limit)."""
    if max_input_tokens is None:
        return
    estimate = estimate_parts_tokens(parts, read_image_size, json.dumps(schema))
    if estimate > max_input_tokens:
        raise AgentError(
            DOCUMENT_SET_TOO_LARGE,
            f"The documents need about {estimate} input tokens; the limit is {max_input_tokens}.",
        )


def make_extraction_check(task: ExtractionTask) -> ResponseCheck:
    """Return the response check: the schema, the status rules, and the allowed record IDs."""
    chunk_ids = {chunk.chunk_id for chunk in task.chunks}

    def check(response: LLMResponse) -> str | None:
        """Return a summary of every problem in the response, or None if it is fine."""
        parsed = parse_response(response.text, ExtractionOutput)
        if isinstance(parsed, str):
            return parsed
        problems = [
            violation.message
            for violation in find_status_violations(parsed, task.field_rules, chunk_ids)
        ]
        problems += find_record_id_problems(parsed, task.allowed_record_ids)
        return summarize_problems(problems) if problems else None

    return check


def find_record_id_problems(output: ExtractionOutput, allowed_ids: frozenset[str]) -> list[str]:
    """Report a record_ref that looks like a record ID but is not one the prompt gave."""
    # Record IDs come from code: the LLM may only echo the IDs it was asked to re-extract
    return [
        f"record_ref {record.record_ref} is not a record_id given in the problems to fix."
        for record in output.records
        if record.record_ref.startswith(RECORD_PREFIX) and record.record_ref not in allowed_ids
    ]
