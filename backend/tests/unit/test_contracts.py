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
)
from app.contracts.chunk import Chunk
from app.contracts.eval_case import EvalCaseInfo
from app.contracts.extraction import ExtractionOutput
from app.contracts.issue import Issue
from app.contracts.judge import JudgeOutput
from app.contracts.log_line import LogLine
from app.contracts.record import (
    FieldOutput,
    RecordExtraction,
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
    "4": StoredRecord,
    "5": Issue,
    "6": ChangesRequest,
    "10": LlmTrace,
    "11": LogLine,
}


def read_contract_examples() -> dict[str, Any]:
    """Return the first JSON example of each numbered CONTRACTS section, parsed."""
    text = CONTRACTS_DOC.read_text(encoding="utf-8")
    matches = list(SECTION_PATTERN.finditer(text))
    examples: dict[str, Any] = {}
    for index, match in enumerate(matches):
        # A section runs from its heading to the next one
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = JSON_BLOCK_PATTERN.search(text, match.end(), end)
        if block is not None:
            examples[match.group(1)] = json.loads(block.group(1))
    return examples


def expand_shorthand_alternatives(stored_record: dict[str, Any]) -> None:
    """Replace the §4 example's `"alternatives": ["..."]` shorthand with full alternatives."""
    for field in stored_record["fields"].values():
        extraction = field["extraction"]
        if extraction is None:
            continue
        extraction["alternatives"] = [
            {"value": item, "evidence": []} if isinstance(item, str) else item
            for item in extraction["alternatives"]
        ]


@pytest.mark.parametrize("section", sorted(EXAMPLE_MODELS))
def test_contract_example_parses(section: str) -> None:
    """The JSON example in each CONTRACTS section is a valid instance of its model."""
    example = read_contract_examples()[section]
    if section == "4":
        expand_shorthand_alternatives(example)
    EXAMPLE_MODELS[section].model_validate(example)


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
    """Build a stored record with an empty output for every loader field."""
    fields = {
        field.key: StoredField(output=FieldOutput(origin="extracted"))
        for field in bundle.field_rules.fields
    }
    return StoredRecord(
        record_id="rec_0001",
        found_in=["doc01-p01-c001"],
        extraction=RecordExtraction(record_ref="R1", record_summary="synthetic record"),
        fields=fields,
    )


def test_record_with_every_field_has_no_problems(bundle: ConfigBundle) -> None:
    """A stored record with all 22 loader fields passes the field check."""
    record = build_full_record(bundle)
    assert len(record.fields) == 22
    assert find_record_field_problems(record, bundle.field_rules) == []


def test_record_missing_a_field_is_reported(bundle: ConfigBundle) -> None:
    """A stored record without one loader field gets a problem naming it."""
    record = build_full_record(bundle)
    missing_key = bundle.field_rules.fields[0].key
    del record.fields[missing_key]
    problems = find_record_field_problems(record, bundle.field_rules)
    assert len(problems) == 1
    assert missing_key in problems[0]


def test_record_with_unknown_field_is_reported(bundle: ConfigBundle) -> None:
    """A stored record with a key the field rules do not define gets a problem."""
    record = build_full_record(bundle)
    record.fields["synthetic_unknown"] = StoredField(output=FieldOutput(origin="system"))
    problems = find_record_field_problems(record, bundle.field_rules)
    assert problems == ["Record rec_0001 has unknown field 'synthetic_unknown'."]
