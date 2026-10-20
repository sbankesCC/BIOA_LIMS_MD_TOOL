"""Eval LLM client: wraps the LLM client to plant seeded errors and keep verification replies.

A case's seeded errors (CONTRACTS §9) are planted into the first extraction response, so the
same graph runs and extraction verification can be scored on catching them. Every verification
response is kept, because the graph stores only the latest findings.
"""

import json
from collections.abc import Sequence
from typing import Any, cast

from app.config.field_rules import FieldRules
from app.contracts.eval_case import SeededError
from app.contracts.trace import LlmNode
from app.llm.client import LLMClient, LLMRequest, LLMResponse
from app.transform.lookup_matching import normalize_for_match

EXTRACTION_NODE = "extraction"
VERIFICATION_NODE = "extraction_verification"


class EvalLLMClient:
    """An LLM client that passes calls on, plants seeded errors, and keeps verification replies."""

    def __init__(
        self, client: LLMClient, seeded: Sequence[SeededError], field_rules: FieldRules
    ) -> None:
        """Wrap `client`; `seeded` errors are planted into the first extraction response."""
        self.client = client
        self.seeded = list(seeded)
        self.field_rules = field_rules
        self.extraction_responses = 0
        self.planted: list[SeededError] = []
        self.verification_texts: list[str] = []

    @property
    def provider(self) -> str:
        """Return the wrapped client's provider."""
        return self.client.provider

    def model_for(self, node: LlmNode) -> str:
        """Return the wrapped client's model for a node."""
        return self.client.model_for(node)

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Send the request on; plant into the first extraction reply, keep verification replies."""
        response = self.client.complete(request)
        if request.node == EXTRACTION_NODE:
            self.extraction_responses += 1
            # Only the first extraction is seeded; a re-extraction may correct the mistake
            if self.extraction_responses == 1 and self.seeded:
                text, self.planted = plant_seeded_errors(
                    response.text, self.seeded, self.field_rules
                )
                response = response.model_copy(update={"text": text})
        elif request.node == VERIFICATION_NODE:
            self.verification_texts.append(response.text)
        return response


def plant_seeded_errors(
    text: str, seeded: Sequence[SeededError], field_rules: FieldRules
) -> tuple[str, list[SeededError]]:
    """Return the extraction text with the seeded values planted, and the errors planted.

    A reply that is not JSON, or a seeded record or field it does not hold, plants nothing.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text, []
    planted: list[SeededError] = []
    for error in seeded:
        record = find_extracted_record(data, error.record, field_rules)
        if record is not None and plant_value(record, error, field_rules):
            planted.append(error)
    if not planted:
        return text, []
    return json.dumps(data, ensure_ascii=False), planted


def find_extracted_record(data: Any, name: str, field_rules: FieldRules) -> dict[str, Any] | None:
    """Return the extracted record whose name matches `name` (ignoring case and spaces)."""
    name_key = field_rules.record_name_field().key
    wanted = normalize_for_match(name)
    for record in read_list(read_dict(data).get("records")):
        value = read_field(record, name_key).get("value")
        if isinstance(value, str) and normalize_for_match(value) == wanted:
            return read_dict(record)
    return None


def read_dict(value: Any) -> dict[str, Any]:
    """Return a JSON object as a dict, or an empty dict for anything else."""
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def read_list(value: Any) -> list[Any]:
    """Return a JSON array as a list, or an empty list for anything else."""
    return cast(list[Any], value) if isinstance(value, list) else []


def read_field(record: Any, key: str) -> dict[str, Any]:
    """Return one field of an extracted record as a dict (empty when it is not there)."""
    return read_dict(read_dict(read_dict(record).get("fields")).get(key))


def plant_value(record: dict[str, Any], error: SeededError, field_rules: FieldRules) -> bool:
    """Set the seeded field to the planted value as `found`; return False if it cannot be."""
    rules = {rule.key: rule for rule in field_rules.extracted_fields()}
    rule = rules.get(error.field)
    fields = read_dict(record.get("fields"))
    if rule is None or error.field not in fields:
        return False
    # The planted value keeps the field's own evidence, else the record name's evidence
    evidence = read_field(record, error.field).get("evidence") or read_field(
        record, field_rules.record_name_field().key
    ).get("evidence")
    if not evidence:
        return False
    value = error.planted_value
    if rule.multi_value and isinstance(value, str):
        value = [value]
    fields[error.field] = {
        "status": "found",
        "value": value,
        "evidence": evidence,
        "alternatives": [],
        "allows_equivalent": False,
        "warning": None,
    }
    return True
