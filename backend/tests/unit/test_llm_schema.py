"""LLM schema tests: built from field rules and models, and accepted by OpenAI strict mode."""

from collections.abc import Iterator
from typing import Any, cast

import pytest

from app.config.bundle import ConfigBundle
from app.llm_schema import (
    build_extraction_schema,
    build_judge_schema,
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


def all_schemas(bundle: ConfigBundle) -> list[dict[str, Any]]:
    """Build every schema sent to the LLM."""
    return [
        build_extraction_schema(bundle.field_rules),
        build_verification_schema(bundle.field_rules),
        build_judge_schema(),
    ]


def test_extraction_schema_has_exactly_the_extracted_fields(bundle: ConfigBundle) -> None:
    """The record's fields are the 17 extracted fields, in field-rules order."""
    properties = field_properties(build_extraction_schema(bundle.field_rules))
    extracted_keys = [field.key for field in bundle.field_rules.extracted_fields()]
    assert list(properties) == extracted_keys
    assert len(properties) == 17


def test_non_extracted_fields_are_not_in_extraction_schema(bundle: ConfigBundle) -> None:
    """Fields with role blank_for_now or system are never sent to the LLM."""
    properties = field_properties(build_extraction_schema(bundle.field_rules))
    other_keys = {field.key for field in bundle.field_rules.fields if field.role != "extracted"}
    assert other_keys
    assert not other_keys & set(properties)


def test_multi_value_field_is_a_list(bundle: ConfigBundle) -> None:
    """A multi_value field's value and alternatives are lists of strings; others are strings."""
    properties = field_properties(build_extraction_schema(bundle.field_rules))
    for field in bundle.field_rules.extracted_fields():
        field_schema = properties[field.key]
        value_type = field_schema["properties"]["value"]["anyOf"][0]["type"]
        alternative = field_schema["properties"]["alternatives"]["items"]
        expected_type = "array" if field.multi_value else "string"
        assert value_type == expected_type
        assert alternative["properties"]["value"]["type"] == expected_type
    assert any(field.multi_value for field in bundle.field_rules.extracted_fields())


def test_field_schema_names_its_column(bundle: ConfigBundle) -> None:
    """Each field's schema description is its DFD column name, read from the field rules."""
    properties = field_properties(build_extraction_schema(bundle.field_rules))
    for field in bundle.field_rules.extracted_fields():
        assert properties[field.key]["description"] == field.column


def test_verification_field_keys_are_limited_to_extracted_fields(bundle: ConfigBundle) -> None:
    """Field findings and unreported conflicts may only name extracted fields."""
    schema = build_verification_schema(bundle.field_rules)
    extracted_keys = [field.key for field in bundle.field_rules.extracted_fields()]
    for list_name in ("field_findings", "unreported_conflicts"):
        item = schema["properties"][list_name]["items"]
        assert item["properties"]["field"]["enum"] == extracted_keys


def test_judge_schema_lists_the_three_verdicts() -> None:
    """The judge may only answer same, different or unsure."""
    item = build_judge_schema()["properties"]["judgments"]["items"]
    assert item["properties"]["verdict"]["enum"] == ["same", "different", "unsure"]


@pytest.mark.parametrize("index", [0, 1, 2])
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
    assert build_extraction_schema(bundle.field_rules) == build_extraction_schema(
        bundle.field_rules
    )
