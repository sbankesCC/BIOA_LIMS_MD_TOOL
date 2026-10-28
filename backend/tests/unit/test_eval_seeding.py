"""Eval seeding tests: seeded errors are planted into the first extraction reply only.

Replies come from the synthetic graph fixtures; field keys come from the client config.
"""

import json

from app.config.bundle import ConfigBundle
from app.contracts.eval_case import SeededError
from app.contracts.extraction import ExtractionOutput
from app.evals.seeding import EvalLLMClient, plant_seeded_errors
from app.llm.client import LLMRequest
from app.llm.fake_client import FakeLLMClient
from tests.fixtures.fake_llm import extraction_reply, verification_reply
from tests.fixtures.make_documents import REAGENT_TABLE

ROW = 1
NAME = REAGENT_TABLE[ROW][0]


def plain_key(bundle: ConfigBundle) -> str:
    """Return an extracted single-value field other than the record name."""
    name_key = bundle.field_rules.record_name_field().key
    return next(
        rule.key
        for rule in bundle.field_rules.extracted_fields()
        if rule.key != name_key and not rule.multi_value
    )


def make_request(node: str) -> LLMRequest:
    """Return a minimal request for one node."""
    return LLMRequest.model_validate(
        {
            "run_id": "run_0001",
            "node": node,
            "prompt_template": node,
            "prompt_version": "1",
            "parts": [],
            "schema_name": node,
            "json_schema": {},
        }
    )


def test_seeded_value_is_planted_as_found(bundle: ConfigBundle) -> None:
    """The planted value replaces the field, found, with the record name's evidence."""
    key = plain_key(bundle)
    error = SeededError(
        record=NAME.lower(),
        field=key,
        planted_value="synthetic plant",
        expected_verdict="unsupported",
    )
    text, planted = plant_seeded_errors(
        extraction_reply(bundle.field_rules, [("R1", ROW)]), [error], bundle.field_rules
    )
    assert planted == [error]
    field = ExtractionOutput.model_validate_json(text).records[0].fields[key]
    assert field.status == "found"
    assert field.value == "synthetic plant"
    assert len(field.evidence) == 1


def test_unknown_record_or_bad_reply_plants_nothing(bundle: ConfigBundle) -> None:
    """A seeded record the reply does not hold, or a reply that is not JSON, is left alone."""
    error = SeededError(
        record="synthetic missing record",
        field=plain_key(bundle),
        planted_value="x",
        expected_verdict="unsupported",
    )
    reply = extraction_reply(bundle.field_rules, [("R1", ROW)])
    assert plant_seeded_errors(reply, [error], bundle.field_rules) == (reply, [])
    assert plant_seeded_errors("not JSON", [error], bundle.field_rules) == ("not JSON", [])


def test_only_the_first_extraction_is_seeded_and_verification_replies_are_kept(
    bundle: ConfigBundle,
) -> None:
    """A re-extraction is passed through unchanged; every verification reply is kept."""
    key = plain_key(bundle)
    error = SeededError(record=NAME, field=key, planted_value="x", expected_verdict="unsupported")
    reply = extraction_reply(bundle.field_rules, [("R1", ROW)])
    fake = FakeLLMClient({"extraction": [reply], "extraction_verification": [verification_reply()]})
    client = EvalLLMClient(fake, [error], bundle.field_rules)
    first = client.complete(make_request("extraction"))
    second = client.complete(make_request("extraction"))
    client.complete(make_request("extraction_verification"))
    assert json.loads(first.text) != json.loads(reply)
    assert second.text == reply
    assert client.planted == [error]
    assert client.verification_texts == [verification_reply()]
    assert client.provider == fake.provider
