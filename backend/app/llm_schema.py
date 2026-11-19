"""JSON Schemas sent to the LLM, generated from the contract models plus `business_rules.md`.

Every schema is OpenAI strict-mode compatible: references inlined, every object closed
(`additionalProperties: false`) with all its properties required, and only supported keywords.
"""

import copy
from typing import Any, cast

from pydantic import BaseModel

from app.config.business_rules import BusinessRules, FieldDefinition
from app.contracts.extraction import ExtractedField, ExtractionOutput
from app.contracts.judge import JudgeOutput
from app.contracts.matching import MatchingOutput
from app.contracts.naming import NamingOutput
from app.contracts.plausibility import PlausibilityOutput
from app.contracts.verification import VerificationOutput

JsonSchema = dict[str, Any]

# Keywords kept from the Pydantic schema; titles, defaults and length limits are dropped
# because strict mode does not accept all of them (status rules check those in code)
KEPT_KEYWORDS = {"type", "properties", "items", "anyOf", "enum", "const"}

STRING_SCHEMA: JsonSchema = {"type": "string"}
STRING_LIST_SCHEMA: JsonSchema = {"type": "array", "items": {"type": "string"}}
NULL_SCHEMA: JsonSchema = {"type": "null"}


def build_extraction_schema(business_rules: BusinessRules) -> JsonSchema:
    """Build the extraction schema: one property per extracted field and per context attribute."""
    schema = build_strict_schema(ExtractionOutput)
    # The model's `context` and `fields` are open mappings; replace them with the configured keys
    record_schema = schema["properties"]["records"]["items"]
    record_schema["properties"]["context"] = build_context_schema(business_rules)
    record_schema["properties"]["fields"] = build_fields_schema(business_rules)
    return schema


def build_verification_schema(business_rules: BusinessRules) -> JsonSchema:
    """Build the verification schema; keys are limited to extracted fields and context keys."""
    schema = build_strict_schema(VerificationOutput)
    keys = [field.key for field in business_rules.extracted_fields()]
    keys += [attribute.key for attribute in business_rules.context_fields()]
    field_key_schema: JsonSchema = {"type": "string", "enum": keys}
    # Both finding lists that name a field may only name an extracted one
    for list_name in ("field_findings", "unreported_conflicts"):
        item_schema = schema["properties"][list_name]["items"]
        item_schema["properties"]["field"] = copy.deepcopy(field_key_schema)
    return schema


def build_judge_schema() -> JsonSchema:
    """Build the duplicate judge schema."""
    return build_strict_schema(JudgeOutput)


def build_matching_schema() -> JsonSchema:
    """Build the Matching schema (code checks each choice against the item's shortlist)."""
    return build_strict_schema(MatchingOutput)


def build_naming_schema() -> JsonSchema:
    """Build the Naming schema (code checks each suggested name)."""
    return build_strict_schema(NamingOutput)


def build_plausibility_schema() -> JsonSchema:
    """Build the plausibility review schema (code drops findings under unknown check IDs)."""
    return build_strict_schema(PlausibilityOutput)


def build_fields_schema(business_rules: BusinessRules) -> JsonSchema:
    """Build the closed `fields` object: one required property per extracted field, in order."""
    base_field_schema = build_strict_schema(ExtractedField)
    properties = {
        field.key: build_field_schema(base_field_schema, field)
        for field in business_rules.extracted_fields()
    }
    return close_object({"type": "object", "properties": properties})


def build_context_schema(business_rules: BusinessRules) -> JsonSchema:
    """Build the closed `context` object: one required property per context attribute, in order."""
    base_field_schema = build_strict_schema(ExtractedField)
    properties = {
        attribute.key: build_value_schema(base_field_schema, is_list=False)
        for attribute in business_rules.context_fields()
    }
    return close_object({"type": "object", "properties": properties})


def build_field_schema(base_field_schema: JsonSchema, field: FieldDefinition) -> JsonSchema:
    """Narrow the generic field schema to one field, described by its column name."""
    schema = build_value_schema(base_field_schema, is_list=field.multi_value)
    # The column name tells the model which loader column this key is
    schema["description"] = field.column
    return schema


def build_value_schema(base_field_schema: JsonSchema, is_list: bool) -> JsonSchema:
    """Narrow the generic field schema's values to a string, or to a list of strings."""
    schema = copy.deepcopy(base_field_schema)
    value_schema = STRING_LIST_SCHEMA if is_list else STRING_SCHEMA
    # The value may be null (not found, conflicting, unclear); an alternative's value may not
    schema["properties"]["value"] = {"anyOf": [copy.deepcopy(value_schema), NULL_SCHEMA]}
    alternative_schema = schema["properties"]["alternatives"]["items"]
    alternative_schema["properties"]["value"] = copy.deepcopy(value_schema)
    return schema


def build_strict_schema(model: type[BaseModel]) -> JsonSchema:
    """Generate a model's JSON Schema and rewrite it into strict-mode form."""
    raw_schema = model.model_json_schema()
    definitions = cast(JsonSchema, raw_schema.get("$defs", {}))
    return make_strict(raw_schema, definitions)


def make_strict(schema: JsonSchema, definitions: JsonSchema) -> JsonSchema:
    """Rewrite one schema node: inline references, keep supported keywords, close objects."""
    # A reference is replaced by the (rewritten) definition it points to
    reference = schema.get("$ref")
    if isinstance(reference, str):
        definition_name = reference.rsplit("/", 1)[-1]
        return make_strict(cast(JsonSchema, definitions[definition_name]), definitions)
    result: JsonSchema = {}
    for keyword, value in schema.items():
        if keyword not in KEPT_KEYWORDS:
            continue
        result[keyword] = make_keyword_strict(keyword, value, definitions)
    if "properties" in result:
        result = close_object(result)
    return result


def make_keyword_strict(keyword: str, value: Any, definitions: JsonSchema) -> Any:
    """Rewrite the sub-schemas held by one keyword; plain values are kept as they are."""
    # `properties` maps names to schemas; `anyOf` is a list of schemas; `items` is one schema
    if keyword == "properties":
        properties = cast(JsonSchema, value)
        return {
            name: make_strict(cast(JsonSchema, sub_schema), definitions)
            for name, sub_schema in properties.items()
        }
    if keyword == "anyOf":
        options = cast(list[JsonSchema], value)
        return [make_strict(option, definitions) for option in options]
    if keyword == "items":
        return make_strict(cast(JsonSchema, value), definitions)
    return value


def close_object(schema: JsonSchema) -> JsonSchema:
    """Mark an object schema closed with every property required, as strict mode needs."""
    closed = dict(schema)
    closed["additionalProperties"] = False
    closed["required"] = list(cast(JsonSchema, schema["properties"]))
    return closed
