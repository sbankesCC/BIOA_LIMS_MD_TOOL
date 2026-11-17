"""Naming agent (ARCHITECTURE §4.7c, CONTRACTS §3c): suggests a Consumable Type name per record.

One call names every record not in the cache, following the naming rules in `prompts/naming.md`
(`rule_id` is stored as the model gave it). Code then checks each name: characters translated,
maximum length, disallowed characters, unique in the run. A failing name is dropped and the
reason (a short code, never the name) is kept in the result. A suggestion never sets the value.
A blank model, a reached call limit or a failed call skips the step (`NAMING_SKIPPED`).
"""

from collections.abc import Mapping, Sequence

from pydantic import BaseModel

from app.agents.common import make_request, parse_response, summarize_problems
from app.agents.step_support import CallBudget, StepCache, call_model_step, make_step_cache_key
from app.config.business_rules import BusinessRules, FieldDefinition
from app.config.prompts import PromptTemplate
from app.contracts.naming import NameAnswer, NamingOutput, NamingRecord
from app.contracts.record import StoredRecord, Suggestion
from app.llm.client import LLMResponse
from app.llm.prompt_builder import build_prompt_parts, format_naming_records
from app.llm.tracing import ResponseCheck, TracedCaller
from app.llm_schema import build_naming_schema
from app.normalization.characters import build_character_map, translate_characters
from app.validation.field_checks import has_disallowed_characters

NODE = "naming"

# Why a suggested name was dropped
EMPTY_NAME = "empty"
TOO_LONG = "too_long"
INVALID_CHARACTERS = "invalid_characters"
DUPLICATE_NAME = "duplicate"


class NamingTask(BaseModel):
    """What one Naming call needs; `model` is None when its setting is blank."""

    run_id: str
    records: list[NamingRecord]
    business_rules: BusinessRules
    template: PromptTemplate
    model: str | None
    # Names already set on records in the run, which a suggestion must not repeat
    taken_names: list[str] = []


class NamingResult(BaseModel):
    """The suggestions that passed the checks by record ID, the drop reasons, and the skip flag."""

    suggestions: dict[str, Suggestion] = {}
    dropped: dict[str, str] = {}
    is_skipped: bool = False


def build_naming_records(
    records: Sequence[StoredRecord], business_rules: BusinessRules
) -> list[NamingRecord]:
    """Return what the model sees of each included record: name as written, values, context."""
    name_key = business_rules.record_name_field().key
    return [
        NamingRecord(
            record_id=record.record_id,
            name_as_written=read_written_value(record, name_key),
            values=read_known_values(record, business_rules, name_key),
            context=read_context_values(record),
        )
        for record in records
        if record.exclusion is None
    ]


def read_written_value(record: StoredRecord, key: str) -> str | None:
    """Return a field's extracted value as one text, or None when there is none."""
    stored = record.fields.get(key)
    value = stored.extraction.value if stored and stored.extraction else None
    if isinstance(value, list):
        return ", ".join(value) or None
    return value or None


def read_known_values(
    record: StoredRecord, business_rules: BusinessRules, name_key: str
) -> dict[str, str]:
    """Return each extracted field's normalized value (as written if it could not be)."""
    values: dict[str, str] = {}
    for rule in business_rules.extracted_fields():
        if rule.key == name_key:
            continue
        stored = record.fields.get(rule.key)
        normalized = stored.normalization.value if stored and stored.normalization else None
        text = normalized or read_matching_or_written(record, rule)
        if text:
            values[rule.key] = text
    return values


def read_matching_or_written(record: StoredRecord, rule: FieldDefinition) -> str | None:
    """Return the text kept for Matching, else the value as written."""
    stored = record.fields.get(rule.key)
    if stored is not None and stored.normalization and stored.normalization.matching_value:
        return stored.normalization.matching_value
    return read_written_value(record, rule.key)


def read_context_values(record: StoredRecord) -> dict[str, str]:
    """Return the context attribute values that were found, by key."""
    values: dict[str, str] = {}
    for key, attribute in record.context.items():
        extraction = attribute.extraction
        if extraction is not None and extraction.status == "found" and extraction.value:
            values[key] = (
                extraction.value
                if isinstance(extraction.value, str)
                else ", ".join(extraction.value)
            )
    return values


def run_naming(
    caller: TracedCaller, task: NamingTask, cache: StepCache, budget: CallBudget
) -> NamingResult:
    """Get an answer per record from the cache or one call, then check each name."""
    answers: dict[str, NameAnswer] = {}
    pending: list[NamingRecord] = []
    for record in task.records:
        cached = cache.get(make_naming_key(task, record))
        if cached is None:
            pending.append(record)
        else:
            answers[record.record_id] = NameAnswer.model_validate_json(cached)
    is_skipped = False
    if pending:
        called = request_names(caller, task, pending, budget)
        if called is None:
            is_skipped = True
        else:
            for record in pending:
                answers[record.record_id] = called[record.record_id]
                cache.put(make_naming_key(task, record), called[record.record_id].model_dump_json())
    result = check_names(task, answers)
    return result.model_copy(update={"is_skipped": is_skipped})


def make_naming_key(task: NamingTask, record: NamingRecord) -> str:
    """Return a record's cache key: its values, rules version, prompt version and model."""
    return make_step_cache_key(
        {
            "record": record.model_dump(mode="json", exclude={"record_id"}),
            "rules": task.business_rules.version,
            "prompt": task.template.version,
            "model": task.model or "",
        }
    )


def request_names(
    caller: TracedCaller, task: NamingTask, pending: list[NamingRecord], budget: CallBudget
) -> dict[str, NameAnswer] | None:
    """Make the one call for the pending records; return the answers by record ID, or None."""
    values = {"records": format_naming_records(pending, task.business_rules)}
    parts = build_prompt_parts(task.template, values)
    request = make_request(task.run_id, NODE, task.template, parts, build_naming_schema())
    ids = [record.record_id for record in pending]
    text = call_model_step(caller, request, make_naming_check(ids), budget, task.model)
    if text is None:
        return None
    return {answer.record_id: answer for answer in NamingOutput.model_validate_json(text).names}


def check_names(task: NamingTask, answers: Mapping[str, NameAnswer]) -> NamingResult:
    """Check each answered name in record order; keep the passing ones and the drop reasons."""
    name_rule = task.business_rules.record_name_field()
    character_map = build_character_map(task.business_rules)
    seen = {name.casefold() for name in task.taken_names}
    result = NamingResult()
    for record in task.records:
        answer = answers.get(record.record_id)
        if answer is None or answer.name is None:
            continue
        name = translate_characters(answer.name, character_map).value.strip()
        reason = find_drop_reason(name, name_rule, seen)
        if reason is not None:
            result.dropped[record.record_id] = reason
            continue
        seen.add(name.casefold())
        result.suggestions[record.record_id] = Suggestion(
            value=name, source="naming", reason=answer.reason, rule_id=answer.rule_id
        )
    return result


def find_drop_reason(name: str, name_rule: FieldDefinition, seen: set[str]) -> str | None:
    """Return why a name fails the code checks, or None when it passes."""
    if not name:
        return EMPTY_NAME
    if name_rule.max_length is not None and len(name) > name_rule.max_length:
        return TOO_LONG
    if has_disallowed_characters(name, name_rule.disallowed_characters):
        return INVALID_CHARACTERS
    if name.casefold() in seen:
        return DUPLICATE_NAME
    return None


def make_naming_check(record_ids: list[str]) -> ResponseCheck:
    """Return the response check: the schema, and exactly one name answer per record."""

    def check(response: LLMResponse) -> str | None:
        """Return a summary of the problems in a Naming response, or None if it is fine."""
        parsed = parse_response(response.text, NamingOutput)
        if isinstance(parsed, str):
            return parsed
        named = [answer.record_id for answer in parsed.names]
        problems = [f"record {i} has no answer." for i in record_ids if i not in named]
        problems += [f"record {i} is not in the request." for i in named if i not in record_ids]
        problems += [
            f"record {i} is answered more than once." for i in set(named) if named.count(i) > 1
        ]
        return summarize_problems(problems) if problems else None

    return check
