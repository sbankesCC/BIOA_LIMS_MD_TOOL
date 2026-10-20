"""Shared agent helpers: the attempt limit, response parsing and the retry prompt.

Problem summaries name only locations, rules, record IDs and field keys, never values, so they
are safe for trace records and retry prompts.
"""

from collections.abc import Sequence

from pydantic import BaseModel, ValidationError

from app.config.prompts import PromptTemplate
from app.contracts.trace import LlmNode
from app.llm.client import LLMRequest, PromptPart, TextPart
from app.llm.tracing import ResponseCheck, TracedCaller, TracedResult

# The structured-output schema name sent with each node's request (OpenAI requires one)
SCHEMA_NAMES: dict[LlmNode, str] = {
    "extraction": "extraction_output",
    "extraction_verification": "verification_output",
    "duplicate_judge": "judge_output",
}

# One retry after a response that breaks the schema or the status rules
MAX_ATTEMPTS = 2

# How many problems a summary lists before it just counts the rest
MAX_LISTED_PROBLEMS = 20

RETRY_HEADING = "# Problems in your previous response"
RETRY_INTRO = "Your previous response broke these rules. Return the whole response again, fixed."


class AgentError(Exception):
    """An agent could not finish; `code` is the run issue code the graph raises for it."""

    def __init__(self, code: str, message: str) -> None:
        """Keep the issue code and a plain message (no document text or values)."""
        super().__init__(message)
        self.code = code


def parse_response[ModelT: BaseModel](text: str, model: type[ModelT]) -> ModelT | str:
    """Parse a JSON response into a model; return a problem summary instead if it does not fit."""
    try:
        return model.model_validate_json(text)
    except ValidationError as error:
        # Only the locations of the errors are kept, never the input values
        places = [".".join(str(step) for step in item["loc"]) or "(top)" for item in error.errors()]
        return summarize_problems(
            [f"{place}: does not fit the schema" for place in places],
        )


def summarize_problems(problems: Sequence[str]) -> str:
    """Join problem messages into one summary, listing at most MAX_LISTED_PROBLEMS."""
    listed = list(problems[:MAX_LISTED_PROBLEMS])
    if len(problems) > MAX_LISTED_PROBLEMS:
        listed.append(f"... and {len(problems) - MAX_LISTED_PROBLEMS} more")
    return "\n".join(f"- {problem}" for problem in listed)


def add_retry_note(parts: Sequence[PromptPart], problem: str) -> list[PromptPart]:
    """Return the prompt parts with the previous response's problems added at the end."""
    note = f"\n\n{RETRY_HEADING}\n{RETRY_INTRO}\n{problem}\n"
    return [*parts, TextPart(text=note)]


def make_request(
    run_id: str,
    node: LlmNode,
    template: PromptTemplate,
    parts: Sequence[PromptPart],
    json_schema: dict[str, object],
) -> LLMRequest:
    """Build an LLM request for a node from its prompt template, parts and schema."""
    return LLMRequest(
        run_id=run_id,
        node=node,
        prompt_template=template.name,
        prompt_version=template.version,
        parts=list(parts),
        schema_name=SCHEMA_NAMES[node],
        json_schema=json_schema,
    )


def call_with_one_retry(
    caller: TracedCaller, request: LLMRequest, check: ResponseCheck
) -> TracedResult:
    """Call the LLM; if the check finds a problem, retry once with the problems in the prompt.

    Returns the last result, whose `problem` is still set when the retry failed too. LLM call
    errors (after the caller's own retries) are raised as LLMCallError.
    """
    result = caller.call(request, 1, check)
    for attempt in range(2, MAX_ATTEMPTS + 1):
        if result.problem is None:
            break
        retry_parts = add_retry_note(request.parts, result.problem)
        retry_request = request.model_copy(update={"parts": retry_parts})
        result = caller.call(retry_request, attempt, check)
    return result
