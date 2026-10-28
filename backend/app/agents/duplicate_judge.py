"""Duplicate judge agent (ARCHITECTURE §4.8, CONTRACTS §3a): the `DuplicateJudge` protocol.

Sends the record's identifying values (the `sent_to_duplicate_judge` fields) and the shortlist.
The response must judge every candidate exactly once; it is retried once. If the judge still
cannot answer, every candidate is "unsure", so the user checks it (validation never sees an error).
"""

from app.agents.common import call_with_one_retry, make_request, parse_response, summarize_problems
from app.config.field_rules import FieldRules
from app.config.prompts import PromptTemplate
from app.contracts.judge import JudgeOutput, Judgment
from app.llm.client import LLMCallError, LLMResponse
from app.llm.prompt_builder import build_prompt_parts, format_candidates, format_judge_record
from app.llm.tracing import ResponseCheck, TracedCaller
from app.llm_schema import build_judge_schema
from app.logging_setup import log_event
from app.validation.judge_cache import JudgeRequest

NODE = "duplicate_judge"

# The reason given for each candidate when the judge could not answer
UNANSWERED_REASON = "The duplicate check could not be completed. Compare this type by hand."


class DuplicateJudgeAgent:
    """The LLM duplicate judge for one run; every call is traced to that run."""

    def __init__(
        self, caller: TracedCaller, run_id: str, template: PromptTemplate, field_rules: FieldRules
    ) -> None:
        """Use the run's traced caller, the judge prompt, and the field rules (column names)."""
        self.caller = caller
        self.run_id = run_id
        self.template = template
        self.field_rules = field_rules

    def judge(self, request: JudgeRequest) -> JudgeOutput:
        """Return one judgment per candidate; all "unsure" if the judge cannot answer."""
        values = {
            "record": format_judge_record(request.values, self.field_rules),
            "candidates": format_candidates(request.candidates),
        }
        parts = build_prompt_parts(self.template, values)
        llm_request = make_request(self.run_id, NODE, self.template, parts, build_judge_schema())
        candidate_ids = [candidate.candidate_id for candidate in request.candidates]
        try:
            result = call_with_one_retry(self.caller, llm_request, make_judge_check(candidate_ids))
        except LLMCallError:
            return self.unanswered(candidate_ids)
        if result.problem is not None:
            return self.unanswered(candidate_ids)
        return JudgeOutput.model_validate_json(result.response.text)

    def unanswered(self, candidate_ids: list[str]) -> JudgeOutput:
        """Return "unsure" for every candidate and log that the judge could not answer."""
        log_event(
            "node_failed",
            level="WARNING",
            run_id=self.run_id,
            node=NODE,
            details={"candidates": len(candidate_ids)},
        )
        return JudgeOutput(
            judgments=[
                Judgment(candidate_id=candidate_id, verdict="unsure", reason=UNANSWERED_REASON)
                for candidate_id in candidate_ids
            ]
        )


def make_judge_check(candidate_ids: list[str]) -> ResponseCheck:
    """Return the response check: the schema, and exactly one judgment per candidate."""

    def check(response: LLMResponse) -> str | None:
        """Return a summary of the problems in a judge response, or None if it is fine."""
        parsed = parse_response(response.text, JudgeOutput)
        if isinstance(parsed, str):
            return parsed
        judged = [judgment.candidate_id for judgment in parsed.judgments]
        problems = [f"candidate {c} has no judgment." for c in candidate_ids if c not in judged]
        problems += [
            f"candidate {c} was not on the shortlist." for c in judged if c not in candidate_ids
        ]
        problems += [
            f"candidate {c} is judged more than once." for c in set(judged) if judged.count(c) > 1
        ]
        return summarize_problems(problems) if problems else None

    return check
