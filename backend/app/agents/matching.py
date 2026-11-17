"""Matching agent (ARCHITECTURE §4.7b, CONTRACTS §3b): suggests list values for unresolved values.

Code builds the items (de-duplicated by field and normalized value) and each item's shortlist.
One call answers every item not in the cache. A choice that is not on the item's shortlist is
rejected. The answer is only a suggestion: this module never sets a value. A blank model, a
reached call limit or a failed call skips the step (the graph adds `MATCHING_SKIPPED`).
"""

from collections.abc import Sequence

from pydantic import BaseModel

from app.agents.common import make_request, parse_response, summarize_problems
from app.agents.step_support import CallBudget, StepCache, call_model_step, make_step_cache_key
from app.config.business_rules import BusinessRules
from app.config.lookup_lists import LookupLists
from app.config.prompts import PromptTemplate
from app.contracts.extraction import Evidence
from app.contracts.matching import MatchingAnswer, MatchingItem, MatchingOutput
from app.contracts.record import StoredRecord
from app.ids import format_numbered_id
from app.llm.client import LLMResponse
from app.llm.prompt_builder import build_matching_rules, build_prompt_parts, format_matching_items
from app.llm.tracing import ResponseCheck, TracedCaller
from app.llm_schema import build_matching_schema
from app.normalization.lookup_matching import find_similar_values, normalize_for_match
from app.normalization.lookup_values import find_allowed_values

NODE = "matching"
ITEM_PREFIX = "m_"

# The step name an exclusion row can name
MATCHING_STEP = "Matching"


class MatchingTarget(BaseModel):
    """One record field a Matching answer applies to."""

    record_id: str
    field: str


class MatchingGroup(BaseModel):
    """One de-duplicated item and every record field that holds its value."""

    item: MatchingItem
    targets: list[MatchingTarget]


class MatchingTask(BaseModel):
    """What one Matching call needs; `model` is None when its setting is blank."""

    run_id: str
    groups: list[MatchingGroup]
    business_rules: BusinessRules
    template: PromptTemplate
    model: str | None


class MatchingResult(BaseModel):
    """The accepted answer per item ID (`choice` None when rejected), and whether it was skipped."""

    answers: dict[str, MatchingAnswer] = {}
    is_skipped: bool = False


def build_matching_groups(
    records: Sequence[StoredRecord],
    business_rules: BusinessRules,
    lookup_lists: LookupLists,
    shortlist_size: int | None,
) -> list[MatchingGroup]:
    """Collect the unresolved lookup values of included records into de-duplicated items."""
    groups: dict[tuple[str, str], MatchingGroup] = {}
    for record in records:
        if record.exclusion is not None:
            continue
        for rule in business_rules.extracted_fields():
            stored = record.fields.get(rule.key)
            value = stored.normalization.matching_value if stored and stored.normalization else None
            if stored is None or value is None:
                continue
            key = (rule.key, normalize_for_match(value))
            target = MatchingTarget(record_id=record.record_id, field=rule.key)
            if key in groups:
                groups[key].targets.append(target)
                continue
            allowed = find_allowed_values(rule, business_rules, lookup_lists, MATCHING_STEP)
            item = MatchingItem(
                item_id=format_numbered_id(ITEM_PREFIX, len(groups) + 1),
                field=rule.column,
                value=value,
                quote=find_quote(stored.extraction.evidence if stored.extraction else []),
                shortlist=find_similar_values(value, allowed, shortlist_size),
            )
            groups[key] = MatchingGroup(item=item, targets=[target])
    return list(groups.values())


def find_quote(evidence: Sequence[Evidence]) -> str:
    """Return the first evidence quote of a field, or an empty text when it has none."""
    return evidence[0].quote if evidence else ""


def run_matching(
    caller: TracedCaller, task: MatchingTask, cache: StepCache, budget: CallBudget
) -> MatchingResult:
    """Answer every item from the cache or one call; skip the step when the call cannot be made."""
    answers: dict[str, MatchingAnswer] = {}
    pending: list[MatchingGroup] = []
    for group in task.groups:
        cached = cache.get(make_matching_key(task, group.item))
        if cached is None:
            pending.append(group)
        else:
            answers[group.item.item_id] = MatchingAnswer.model_validate_json(cached)
    if not pending:
        return MatchingResult(answers=answers)
    called = request_matching(caller, task, pending, budget)
    if called is None:
        return MatchingResult(answers=answers, is_skipped=True)
    for group in pending:
        accepted = reject_off_shortlist(called[group.item.item_id], group.item)
        answers[group.item.item_id] = accepted
        cache.put(make_matching_key(task, group.item), accepted.model_dump_json())
    return MatchingResult(answers=answers)


def make_matching_key(task: MatchingTask, item: MatchingItem) -> str:
    """Return an item's cache key: field, value, shortlist, rules version, prompt, model."""
    return make_step_cache_key(
        {
            "field": item.field,
            "value": item.value,
            "shortlist": item.shortlist,
            "rules": task.business_rules.version,
            "prompt": task.template.version,
            "model": task.model or "",
        }
    )


def request_matching(
    caller: TracedCaller, task: MatchingTask, pending: list[MatchingGroup], budget: CallBudget
) -> dict[str, MatchingAnswer] | None:
    """Make the one call for the pending items; return the answers by item ID, or None to skip."""
    items = [group.item for group in pending]
    field_keys = [target.field for group in pending for target in group.targets]
    values = {
        "matching_rules": build_matching_rules(task.business_rules, field_keys),
        "items": format_matching_items(items),
    }
    parts = build_prompt_parts(task.template, values)
    request = make_request(task.run_id, NODE, task.template, parts, build_matching_schema())
    text = call_model_step(
        caller, request, make_matching_check([item.item_id for item in items]), budget, task.model
    )
    if text is None:
        return None
    return {answer.item_id: answer for answer in MatchingOutput.model_validate_json(text).answers}


def reject_off_shortlist(answer: MatchingAnswer, item: MatchingItem) -> MatchingAnswer:
    """Return the answer, or the same answer with no choice when the choice is not shortlisted."""
    if answer.choice is None or answer.choice in item.shortlist:
        return answer
    return MatchingAnswer(item_id=answer.item_id, choice=None, reason=answer.reason)


def make_matching_check(item_ids: list[str]) -> ResponseCheck:
    """Return the response check: the schema, and exactly one answer per item."""

    def check(response: LLMResponse) -> str | None:
        """Return a summary of the problems in a Matching response, or None if it is fine."""
        parsed = parse_response(response.text, MatchingOutput)
        if isinstance(parsed, str):
            return parsed
        answered = [answer.item_id for answer in parsed.answers]
        problems = [f"item {i} has no answer." for i in item_ids if i not in answered]
        problems += [f"item {i} is not in the request." for i in answered if i not in item_ids]
        problems += [
            f"item {i} is answered more than once." for i in set(answered) if answered.count(i) > 1
        ]
        return summarize_problems(problems) if problems else None

    return check
