"""Field rules (`field_rules.yaml`): loader fields, their roles and checks, and condition groups.

Field order here is the column order of the DFD loader. Flags mark the record name field and the
fields sent to the duplicate judge. Cross-file checks live in `bundle.py`.
"""

import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.config.errors import ConfigError, parse_model, read_yaml

FILE_NAME = "field_rules.yaml"

# Field keys are snake_case: they map to DFD column names and appear in every contract
FIELD_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

FieldRole = Literal["extracted", "blank_for_now", "system"]
Requirement = Literal["required", "conditional", "optional"]
FieldType = Literal["text", "decimal", "integer", "boolean"]
DisallowedCharacters = Literal["greek_letters", "control_characters"]


class FieldRule(BaseModel):
    """One loader field: its DFD column, role, requirement, type and limits."""

    model_config = ConfigDict(extra="forbid")

    key: str
    column: str = Field(min_length=1)
    role: FieldRole
    requirement: Requirement
    type: FieldType
    max_length: int | None = Field(default=None, gt=0)
    lookup_sheet: str | None = None
    default: str | None = None
    multi_value: bool = False
    separator: str | None = None
    disallowed_characters: list[DisallowedCharacters] = []
    notes: str | None = None
    extraction_guidance: str | None = None
    is_record_name: bool = False
    sent_to_duplicate_judge: bool = False


class OneOfGroup(BaseModel):
    """Condition group: at least one option (a set of fields) must be completely filled."""

    model_config = ConfigDict(extra="forbid")

    source: str
    rule: Literal["one_of"]
    options: list[list[str]] = Field(min_length=2)
    issue_code: str


class BothOrNeitherGroup(BaseModel):
    """Condition group: the fields are either all filled or all empty."""

    model_config = ConfigDict(extra="forbid")

    source: str
    rule: Literal["both_or_neither"]
    fields: list[str] = Field(min_length=2)
    issue_code: str


ConditionGroup = Annotated[OneOfGroup | BothOrNeitherGroup, Field(discriminator="rule")]


class FieldRules(BaseModel):
    """The whole field rules file."""

    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1)
    placeholder_value: str = Field(min_length=1)
    fields: list[FieldRule] = Field(min_length=1)
    condition_groups: dict[str, ConditionGroup] = {}

    def extracted_fields(self) -> list[FieldRule]:
        """Return the fields the LLM extracts, in loader order."""
        return [field for field in self.fields if field.role == "extracted"]

    def columns(self) -> list[str]:
        """Return the DFD column names in loader order."""
        return [field.column for field in self.fields]

    def record_name_field(self) -> FieldRule:
        """Return the field flagged `is_record_name` (loading checks exactly one has it)."""
        return next(field for field in self.fields if field.is_record_name)

    def duplicate_judge_fields(self) -> list[FieldRule]:
        """Return the fields sent to the duplicate judge (and its cache key), in loader order."""
        return [field for field in self.fields if field.sent_to_duplicate_judge]


def load_field_rules(path: Path) -> FieldRules:
    """Load `field_rules.yaml` and check it on its own; raise ConfigError on any problem."""
    rules = parse_model(FieldRules, read_yaml(path), FILE_NAME)
    problems = (
        find_field_problems(rules)
        + find_flag_problems(rules)
        + find_condition_group_problems(rules)
    )
    if problems:
        raise ConfigError(problems)
    return rules


def find_field_problems(rules: FieldRules) -> list[str]:
    """Check keys and columns are unique and each field's settings fit its role and type."""
    problems: list[str] = []
    seen_keys: set[str] = set()
    seen_columns: set[str] = set()
    for field in rules.fields:
        # Keys and columns identify a field everywhere, so both must be unique
        if not FIELD_KEY_PATTERN.match(field.key):
            problems.append(f"{FILE_NAME}: field key '{field.key}' must be snake_case.")
        if field.key in seen_keys:
            problems.append(f"{FILE_NAME}: field key '{field.key}' is used twice.")
        if field.column in seen_columns:
            problems.append(f"{FILE_NAME}: column '{field.column}' is used twice.")
        seen_keys.add(field.key)
        seen_columns.add(field.column)
        problems.extend(find_settings_problems(field))
    return problems


def find_settings_problems(field: FieldRule) -> list[str]:
    """Check one field's settings are consistent with its role and type."""
    problems: list[str] = []
    name = f"{FILE_NAME}: field '{field.key}'"
    # The LLM needs guidance for every field it extracts
    if field.role == "extracted" and not field.extraction_guidance:
        problems.append(f"{name} is extracted but has no extraction_guidance.")
    # Only extracted fields can hold several values (the LLM returns a list)
    if field.multi_value and field.role != "extracted":
        problems.append(f"{name} has multi_value but is not extracted.")
    if field.multi_value and not field.separator:
        problems.append(f"{name} has multi_value but no separator.")
    # Defaults are filled by transformation, which only handles extracted fields
    if field.default is not None and field.role != "extracted":
        problems.append(f"{name} has a default but is not extracted.")
    # Lookup lists hold text values, so a lookup field must be text
    if field.lookup_sheet and field.type != "text":
        problems.append(f"{name} has a lookup_sheet but its type is {field.type}, not text.")
    return problems


def find_flag_problems(rules: FieldRules) -> list[str]:
    """Check exactly one field names a record and that field is sent to the duplicate judge."""
    problems: list[str] = []
    name_fields = [field for field in rules.fields if field.is_record_name]
    # Duplicate checks, review and audit need exactly one record name field
    if len(name_fields) != 1:
        problems.append(
            f"{FILE_NAME}: exactly one field must have is_record_name: true, "
            f"but {len(name_fields)} do. Mark the field that names a record, and only that one."
        )
    # The judge compares names, so the name must be among the fields it sees
    for field in name_fields:
        if not field.sent_to_duplicate_judge:
            problems.append(
                f"{FILE_NAME}: field '{field.key}' has is_record_name but not "
                "sent_to_duplicate_judge. Add sent_to_duplicate_judge: true to it."
            )
    return problems


def find_condition_group_problems(rules: FieldRules) -> list[str]:
    """Check condition groups name real fields and every conditional field is in a group."""
    problems: list[str] = []
    known_keys = {field.key for field in rules.fields}
    grouped_keys: set[str] = set()
    for group_name, group in rules.condition_groups.items():
        for key in fields_in_group(group):
            grouped_keys.add(key)
            if key not in known_keys:
                problems.append(
                    f"{FILE_NAME}: condition group '{group_name}' names unknown field '{key}'."
                )
    for field in rules.fields:
        if field.requirement == "conditional" and field.key not in grouped_keys:
            problems.append(
                f"{FILE_NAME}: field '{field.key}' is conditional but in no condition group."
            )
    return problems


def fields_in_group(group: OneOfGroup | BothOrNeitherGroup) -> list[str]:
    """Return every field key a condition group uses."""
    if isinstance(group, OneOfGroup):
        return [key for option in group.options for key in option]
    return list(group.fields)
