"""LLM schema tests: built from business rules and models, and accepted by OpenAI strict mode."""

from collections.abc import Iterator
from typing import Any, cast

import pytest

from app.config.bundle import ConfigBundle
from app.llm_schema import (
    build_extraction_schema,
    build_judge_schema,
    build_matching_schema,
    build_naming_schema,
    build_plausibility_schema,
    build_verification_schema,
)

# Keywords the generated schemas may use (a subset of what strict mode supports)
ALLOWED_KEYWORDS = {
    "type",
    "properties",
    "items",
    "anyOf",
    "enum",
    "const",
    "required",
    "additionalProperties",
    "description",
}


def walk_schemas(schema: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield a schema and every sub-schema inside it."""
    yield schema
    for name, sub_schema in schema.get("properties", {}).items():
        assert isinstance(name, str)
        yield from walk_schemas(sub_schema)
    if "items" in schema:
        yield from walk_schemas(schema["items"])
    for option in schema.get("anyOf", []):
        yield from walk_schemas(option)


def field_properties(schema: dict[str, Any]) -> dict[str, Any]:
    """Return the per-field properties of an extraction schema's record."""
    record_schema = schema["properties"]["records"]["items"]
    return cast(dict[str, Any], record_schema["properties"]["fields"]["properties"])


def context_properties(schema: dict[str, Any]) -> dict[str, Any]:
    """Return the per-attribute properties of an extraction schema's record context."""
    record_schema = schema["properties"]["records"]["items"]
    return cast(dict[str, Any], record_schema["properties"]["context"]["properties"])


def all_schemas(bundle: ConfigBundle) -> list[dict[str, Any]]:
    """Build every schema sent to the LLM."""
    return [
        build_extraction_schema(bundle.business_rules),
        build_verification_schema(bundle.business_rules),
        build_judge_schema(),
        build_matching_schema(),
        build_naming_schema(),
        build_plausibility_schema(),
    ]


def test_extraction_schema_has_exactly_the_extracted_fields(bundle: ConfigBundle) -> None:
    """The record's fields are the 13 extracted and generated fields, in loader order."""
    properties = field_properties(build_extraction_schema(bundle.business_rules))
    extracted_keys = [field.key for field in bundle.business_rules.extracted_fields()]
    assert list(properties) == extracted_keys
    assert len(properties) == 13


def test_non_extracted_fields_are_not_in_extraction_schema(bundle: ConfigBundle) -> None:
    """Derived, system and blank_for_now fields are never sent to the LLM for extraction."""
    properties = field_properties(build_extraction_schema(bundle.business_rules))
    other_keys = {field.key for field in bundle.business_rules.fields if not field.is_extracted}
    assert other_keys
    assert not other_keys & set(properties)


def test_multi_value_field_is_a_list(bundle: ConfigBundle) -> None:
    """A multi_value field's value and alternatives are lists of strings; others are strings."""
    properties = field_properties(build_extraction_schema(bundle.business_rules))
    for field in bundle.business_rules.extracted_fields():
        field_schema = properties[field.key]
        value_type = field_schema["properties"]["value"]["anyOf"][0]["type"]
        alternative = field_schema["properties"]["alternatives"]["items"]
        expected_type = "array" if field.multi_value else "string"
        assert value_type == expected_type
        assert alternative["properties"]["value"]["type"] == expected_type
    assert any(field.multi_value for field in bundle.business_rules.extracted_fields())


def test_field_schema_names_its_column(bundle: ConfigBundle) -> None:
    """Each field's schema description is its DFD column name, read from the business rules."""
    properties = field_properties(build_extraction_schema(bundle.business_rules))
    for field in bundle.business_rules.extracted_fields():
        assert properties[field.key]["description"] == field.column


def test_extraction_schema_has_every_context_attribute(bundle: ConfigBundle) -> None:
    """The record's context has one property per context attribute, each a single string."""
    properties = context_properties(build_extraction_schema(bundle.business_rules))
    context_keys = [attribute.key for attribute in bundle.business_rules.context_fields()]
    assert list(properties) == context_keys
    for attribute_schema in properties.values():
        assert attribute_schema["properties"]["value"]["anyOf"][0] == {"type": "string"}
        alternative = attribute_schema["properties"]["alternatives"]["items"]
        assert alternative["properties"]["value"] == {"type": "string"}


def test_extraction_schema_allows_unclear_and_drops_allows_equivalent(
    bundle: ConfigBundle,
) -> None:
    """Every field may be `unclear`, and `allows_equivalent` is gone."""
    properties = field_properties(build_extraction_schema(bundle.business_rules))
    for field_schema in properties.values():
        assert "unclear" in field_schema["properties"]["status"]["enum"]
        assert "allows_equivalent" not in field_schema["properties"]


def test_verification_keys_are_extracted_fields_and_context(bundle: ConfigBundle) -> None:
    """Field findings and unreported conflicts name an extracted field or a context attribute."""
    schema = build_verification_schema(bundle.business_rules)
    rules = bundle.business_rules
    expected_keys = [field.key for field in rules.extracted_fields()]
    expected_keys += [attribute.key for attribute in rules.context_fields()]
    for list_name in ("field_findings", "unreported_conflicts"):
        item = schema["properties"][list_name]["items"]
        assert item["properties"]["field"]["enum"] == expected_keys
        assert item["properties"]["section"]["enum"] == ["fields", "context"]


def test_verification_schema_has_the_incomplete_verdict(bundle: ConfigBundle) -> None:
    """The agent may report a value as `incomplete`."""
    schema = build_verification_schema(bundle.business_rules)
    item = schema["properties"]["field_findings"]["items"]
    assert "incomplete" in item["properties"]["verdict"]["enum"]


def test_matching_choice_may_be_null() -> None:
    """A Matching answer is a shortlist value or null, with a reason."""
    item = build_matching_schema()["properties"]["answers"]["items"]
    assert item["required"] == ["item_id", "choice", "reason"]
    assert {"type": "null"} in item["properties"]["choice"]["anyOf"]


def test_naming_name_and_rule_id_may_be_null() -> None:
    """A Naming answer may give no name and no rule, with a reason."""
    item = build_naming_schema()["properties"]["names"]["items"]
    assert item["required"] == ["record_id", "name", "rule_id", "reason"]
    for key in ("name", "rule_id"):
        assert {"type": "null"} in item["properties"][key]["anyOf"]


def test_plausibility_finding_lists_fields() -> None:
    """A plausibility finding names its check, the fields involved and a reason."""
    item = build_plausibility_schema()["properties"]["findings"]["items"]
    assert item["required"] == ["record_id", "check_id", "fields", "reason"]
    assert item["properties"]["fields"] == {"type": "array", "items": {"type": "string"}}


def test_judge_schema_lists_the_three_verdicts() -> None:
    """The judge may only answer same, different or unsure."""
    item = build_judge_schema()["properties"]["judgments"]["items"]
    assert item["properties"]["verdict"]["enum"] == ["same", "different", "unsure"]


@pytest.mark.parametrize("index", range(6))
def test_schemas_are_strict_mode_compatible(bundle: ConfigBundle, index: int) -> None:
    """Every object is closed with all properties required, and only known keywords are used."""
    schema = all_schemas(bundle)[index]
    assert schema["type"] == "object"
    for sub_schema in walk_schemas(schema):
        assert set(sub_schema) <= ALLOWED_KEYWORDS
        if sub_schema.get("type") == "object":
            assert sub_schema["additionalProperties"] is False
            assert sub_schema["required"] == list(sub_schema["properties"])


def test_building_twice_gives_the_same_schema(bundle: ConfigBundle) -> None:
    """Schemas are generated deterministically, so traces and caches stay comparable."""
    assert build_extraction_schema(bundle.business_rules) == build_extraction_schema(
        bundle.business_rules
    )
