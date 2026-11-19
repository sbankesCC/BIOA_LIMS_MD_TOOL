"""Contract model tests: every JSON example in docs/CONTRACTS.md parses into its model.

Examples are read from the doc itself, so a change to either the doc or a model shows up here.
"""

import json
import re
from typing import Any

import pytest
import yaml
from pydantic import BaseModel, ValidationError

from app.config.bundle import ConfigBundle
from app.contracts.changes import (
    AcceptWarningChange,
    ChangesRequest,
    ExcludeRecordChange,
    PickAlternativeChange,
    SetValueChange,
    UseSuggestionChange,
)
from app.contracts.chunk import Chunk
from app.contracts.eval_case import EvalCaseInfo
from app.contracts.extraction import ExtractionOutput
from app.contracts.issue import Issue
from app.contracts.judge import JudgeOutput
from app.contracts.log_line import LogLine
from app.contracts.matching import MatchingItem, MatchingOutput
from app.contracts.naming import NamingOutput
from app.contracts.plausibility import PlausibilityOutput
from app.contracts.record import (
    FieldOutput,
    RecordExtraction,
    StoredContextAttribute,
    StoredField,
    StoredRecord,
    find_record_field_problems,
)
from app.contracts.trace import LlmTrace
from app.contracts.verification import VerificationOutput
from app.logging_setup import build_log_line
from app.settings import PROJECT_ROOT

CONTRACTS_DOC = PROJECT_ROOT / "docs" / "CONTRACTS.md"
CASE_TEMPLATE = PROJECT_ROOT / "evals" / "cases" / "_template" / "case.yaml"

SECTION_PATTERN = re.compile(r"^## (\w+)\. ", re.MULTILINE)
JSON_BLOCK_PATTERN = re.compile(r"```json\n(.*?)```", re.DOTALL)

# CONTRACTS section number -> the model its first JSON example must parse into
EXAMPLE_MODELS: dict[str, type[BaseModel]] = {
    "1": Chunk,
    "2": ExtractionOutput,
    "3": VerificationOutput,
    "3a": JudgeOutput,
    "3b": MatchingItem,
    "3c": NamingOutput,
    "3d": PlausibilityOutput,
    "4": StoredRecord,
    "5": Issue,
    "6": ChangesRequest,
    "10": LlmTrace,
    "11": LogLine,
}


def read_all_contract_examples() -> dict[str, list[Any]]:
    """Return every JSON example of each numbered CONTRACTS section, parsed, in order."""
    text = CONTRACTS_DOC.read_text(encoding="utf-8")
    matches = list(SECTION_PATTERN.finditer(text))
    examples: dict[str, list[Any]] = {}
    for index, match in enumerate(matches):
        # A section runs from its heading to the next one
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks = JSON_BLOCK_PATTERN.finditer(text, match.end(), end)
        parsed = [json.loads(block.group(1)) for block in blocks]
        if parsed:
            examples[match.group(1)] = parsed
    return examples


def read_contract_examples() -> dict[str, Any]:
    """Return the first JSON example of each numbered CONTRACTS section, parsed."""
    return {section: blocks[0] for section, blocks in read_all_contract_examples().items()}


def expand_shorthand(stored_record: dict[str, Any]) -> None:
    """Replace the §4 example's `["..."]` shorthand for evidence and alternatives."""
    entries = [*stored_record["fields"].values(), *stored_record["context"].values()]
    for entry in entries:
        extraction = entry["extraction"]
        if extraction is None:
            continue
        extraction["evidence"] = [
            {"chunk_id": item, "quote": item} if isinstance(item, str) else item
            for item in extraction["evidence"]
        ]
        extraction["alternatives"] = [
            {"value": item, "evidence": []} if isinstance(item, str) else item
            for item in extraction["alternatives"]
        ]


@pytest.mark.parametrize("section", sorted(EXAMPLE_MODELS))
def test_contract_example_parses(section: str) -> None:
    """The JSON example in each CONTRACTS section is a valid instance of its model."""
    example = read_contract_examples()[section]
    if section == "4":
        expand_shorthand(example)
    EXAMPLE_MODELS[section].model_validate(example)


def test_matching_response_example_parses() -> None:
    """The second §3b example (the Matching response) is a valid response."""
    response = read_all_contract_examples()["3b"][1]
    output = MatchingOutput.model_validate(response)
    assert [answer.choice is None for answer in output.answers] == [False, True]


def test_stored_record_example_has_context_and_suggestion() -> None:
    """The §4 example keeps context apart from fields, with a suggestion and a derived origin."""
    example = read_contract_examples()["4"]
    expand_shorthand(example)
    record = StoredRecord.model_validate(example)
    assert record.context and all(entry.extraction for entry in record.context.values())
    suggestions = [field.suggestion for field in record.fields.values() if field.suggestion]
    assert [suggestion.source for suggestion in suggestions] == ["matching"]
    assert "derived" in {field.output.origin for field in record.fields.values()}


def test_every_contract_example_is_checked() -> None:
    """Every section with a JSON example is covered, except the API error shape (§13, M9)."""
    sections_with_examples = set(read_contract_examples())
    assert sections_with_examples - set(EXAMPLE_MODELS) == {"13"}


def test_change_types_are_chosen_by_type_key() -> None:
    """Each change in the §6 example becomes the model for its `type`."""
    request = ChangesRequest.model_validate(read_contract_examples()["6"])
    kinds = [type(change) for change in request.changes]
    assert kinds == [
        PickAlternativeChange,
        AcceptWarningChange,
        ExcludeRecordChange,
        SetValueChange,
        UseSuggestionChange,
    ]


def test_exclude_without_reason_is_rejected() -> None:
    """An exclude_record change must give a reason."""
    with pytest.raises(ValidationError):
        ChangesRequest.model_validate(
            {
                "user": "synthetic user",
                "timestamp": "2026-10-16T14:05:00Z",
                "changes": [
                    {"change_id": "chg_1", "type": "exclude_record", "record_id": "rec_0001"}
                ],
            }
        )


def test_unknown_change_type_is_rejected() -> None:
    """A change type outside CONTRACTS §6 is refused."""
    with pytest.raises(ValidationError):
        ChangesRequest.model_validate(
            {
                "user": "synthetic user",
                "timestamp": "2026-10-16T14:05:00Z",
                "changes": [{"change_id": "chg_1", "type": "delete_everything"}],
            }
        )


def test_unknown_keys_are_rejected() -> None:
    """Contract models refuse keys their contract does not define."""
    example = read_contract_examples()["5"]
    example["surprise"] = 1
    with pytest.raises(ValidationError):
        Issue.model_validate(example)


def test_log_lines_from_logging_match_the_contract() -> None:
    """A line built by the logger parses as a §11 log line."""
    line = build_log_line("node_finished", run_id="run_0001", details={"records_found": 3})
    LogLine.model_validate(line)


def test_eval_case_template_parses() -> None:
    """The eval case template's `case.yaml` is a valid §9 case description."""
    data = yaml.safe_load(CASE_TEMPLATE.read_text(encoding="utf-8"))
    EvalCaseInfo.model_validate(data)


def build_full_record(bundle: ConfigBundle) -> StoredRecord:
    """Build a stored record with an empty entry for every context attribute and loader field."""
    fields = {
        field.key: StoredField(output=FieldOutput(origin="extracted"))
        for field in bundle.business_rules.fields
    }
    context = {
        attribute.key: StoredContextAttribute()
        for attribute in bundle.business_rules.context_fields()
    }
    return StoredRecord(
        record_id="rec_0001",
        found_in=["doc01-p01-c001"],
        extraction=RecordExtraction(record_ref="R1", record_summary="synthetic record"),
        context=context,
        fields=fields,
    )


def test_record_with_every_field_has_no_problems(bundle: ConfigBundle) -> None:
    """A stored record with all 22 loader fields and both context attributes passes the check."""
    record = build_full_record(bundle)
    assert (len(record.fields), len(record.context)) == (22, 2)
    assert find_record_field_problems(record, bundle.business_rules) == []


def test_record_missing_a_context_attribute_is_reported(bundle: ConfigBundle) -> None:
    """A stored record without one context attribute gets a problem naming it."""
    record = build_full_record(bundle)
    missing_key = bundle.business_rules.context_fields()[0].key
    del record.context[missing_key]
    problems = find_record_field_problems(record, bundle.business_rules)
    assert problems == [f"Record rec_0001 has no entry for context attribute '{missing_key}'."]


def test_record_missing_a_field_is_reported(bundle: ConfigBundle) -> None:
    """A stored record without one loader field gets a problem naming it."""
    record = build_full_record(bundle)
    missing_key = bundle.business_rules.fields[0].key
    del record.fields[missing_key]
    problems = find_record_field_problems(record, bundle.business_rules)
    assert len(problems) == 1
    assert missing_key in problems[0]


def test_record_with_unknown_field_is_reported(bundle: ConfigBundle) -> None:
    """A stored record with a key the business rules do not define gets a problem."""
    record = build_full_record(bundle)
    record.fields["synthetic_unknown"] = StoredField(output=FieldOutput(origin="system"))
    problems = find_record_field_problems(record, bundle.business_rules)
    assert problems == ["Record rec_0001 has unknown field 'synthetic_unknown'."]
