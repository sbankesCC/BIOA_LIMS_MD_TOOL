"""Plausibility agent (ARCHITECTURE §4.8, CONTRACTS §3d): asks whether values fit together.

Called from Validation once per pass, only when `business_rules.md` has an active
`[Plausibility]` check, and only with values that passed the field checks. A finding under an
unknown check ID, or naming no field, is dropped. Results are cached per record. A blank model,
a reached call limit or a failed call skips the step (`PLAUSIBILITY_SKIPPED`).
"""

from collections.abc import Sequence

from pydantic import BaseModel

from app.agents.common import make_request, parse_response
from app.agents.step_support import CallBudget, StepCache, call_model_step, make_step_cache_key
from app.config.business_rules import BusinessRules
from app.config.prompts import PromptTemplate
from app.contracts.plausibility import PlausibilityFinding, PlausibilityOutput, PlausibilityRecord
from app.llm.client import LLMResponse
from app.llm.prompt_builder import build_checks, build_prompt_parts, format_plausibility_records
from app.llm.tracing import ResponseCheck, TracedCaller
from app.llm_schema import build_plausibility_schema

NODE = "plausibility"


class PlausibilityTask(BaseModel):
    """What the review needs; `model` is None when its setting is blank."""

    run_id: str
    records: list[PlausibilityRecord]
    business_rules: BusinessRules
    template: PromptTemplate
    model: str | None


class PlausibilityResult(BaseModel):
    """The findings that were kept, and whether the step was skipped."""

    findings: list[PlausibilityFinding] = []
    is_skipped: bool = False


def find_active_check_ids(business_rules: BusinessRules) -> list[str]:
    """Return the IDs of the active [Plausibility] checks (none means no call is made)."""
    return [rule.rule_id for rule in business_rules.rules_for("Plausibility")]


def run_plausibility(
    caller: TracedCaller, task: PlausibilityTask, cache: StepCache, budget: CallBudget
) -> PlausibilityResult:
    """Review the records from the cache or one call; drop findings that cannot be used."""
    check_ids = find_active_check_ids(task.business_rules)
    if not check_ids or not task.records:
        return PlausibilityResult()
    found: dict[str, list[PlausibilityFinding]] = {}
    pending: list[PlausibilityRecord] = []
    for record in task.records:
        cached = cache.get(make_plausibility_key(task, record))
        if cached is None:
            pending.append(record)
        else:
            found[record.record_id] = PlausibilityOutput.model_validate_json(cached).findings
    is_skipped = False
    if pending:
        called = request_findings(caller, task, pending, check_ids, budget)
        if called is None:
            is_skipped = True
        else:
            store_findings(task, cache, pending, called, found)
    kept = [f for record in task.records for f in found.get(record.record_id, [])]
    return PlausibilityResult(findings=kept, is_skipped=is_skipped)


def store_findings(
    task: PlausibilityTask,
    cache: StepCache,
    pending: Sequence[PlausibilityRecord],
    called: Sequence[PlausibilityFinding],
    found: dict[str, list[PlausibilityFinding]],
) -> None:
    """Group the call's findings by record and cache each record's (also when it has none)."""
    for record in pending:
        own = [finding for finding in called if finding.record_id == record.record_id]
        found[record.record_id] = own
        output = PlausibilityOutput(findings=own)
        cache.put(make_plausibility_key(task, record), output.model_dump_json())


def make_plausibility_key(task: PlausibilityTask, record: PlausibilityRecord) -> str:
    """Return a record's cache key: its values, rules version, prompt version and model."""
    return make_step_cache_key(
        {
            "record": record.model_dump(mode="json", exclude={"record_id"}),
            "rules": task.business_rules.version,
            "prompt": task.template.version,
            "model": task.model or "",
        }
    )


def request_findings(
    caller: TracedCaller,
    task: PlausibilityTask,
    pending: list[PlausibilityRecord],
    check_ids: list[str],
    budget: CallBudget,
) -> list[PlausibilityFinding] | None:
    """Make the one call; return the usable findings, or None to skip the step."""
    values = {
        "checks": build_checks(task.business_rules),
        "records": format_plausibility_records(pending),
    }
    parts = build_prompt_parts(task.template, values)
    request = make_request(task.run_id, NODE, task.template, parts, build_plausibility_schema())
    text = call_model_step(caller, request, make_plausibility_check(), budget, task.model)
    if text is None:
        return None
    asked = {record.record_id for record in pending}
    findings = PlausibilityOutput.model_validate_json(text).findings
    return [f for f in findings if f.check_id in check_ids and f.fields and f.record_id in asked]


def make_plausibility_check() -> ResponseCheck:
    """Return the response check: the response must fit the schema."""

    def check(response: LLMResponse) -> str | None:
        """Return a summary of the problems in a plausibility response, or None if it is fine."""
        parsed = parse_response(response.text, PlausibilityOutput)
        return parsed if isinstance(parsed, str) else None

    return check


class PlausibilityAgent:
    """The plausibility reviewer of one validation pass (implements `PlausibilityReviewer`)."""

    def __init__(
        self,
        caller: TracedCaller,
        run_id: str,
        business_rules: BusinessRules,
        template: PromptTemplate,
        model: str | None,
        cache: StepCache,
        budget: CallBudget,
    ) -> None:
        """Keep what each review needs; `model` is None when its setting is blank."""
        self.caller = caller
        self.run_id = run_id
        self.business_rules = business_rules
        self.template = template
        self.model = model
        self.cache = cache
        self.budget = budget

    def review(self, records: list[PlausibilityRecord]) -> PlausibilityResult:
        """Review the records (cache first, then one call for the rest)."""
        task = PlausibilityTask(
            run_id=self.run_id,
            records=records,
            business_rules=self.business_rules,
            template=self.template,
            model=self.model,
        )
        return run_plausibility(self.caller, task, self.cache, self.budget)
