"""Extraction rules (`extraction_rules.md`): the guidance the extraction prompts read.

Same Markdown grammar as `business_rules.md`: general rules and candidate criteria under
`## General rules`, then one `## Field: <key>` section of [Extraction] lines per extracted field and
context attribute. The fields themselves (key, column, type) are defined in `business_rules.md`.
"""

from pathlib import Path

from pydantic import BaseModel, Field

from app.config.business_rules import (
    CANDIDATE_HEADING,
    EXTRACTION_RULES_FILE,
    FIELD_PREFIX,
    BusinessRules,
    RawDocument,
    RuleLine,
    build_rule_line,
    read_markdown,
    read_version,
)
from app.config.business_rules import FILE_NAME as BUSINESS_RULES_FILE
from app.config.business_rules_checks import (
    find_key_problems,
    find_rule_line_problems,
    find_version_problems,
    repeated,
)
from app.config.errors import ConfigError, require_file

FILE_NAME = EXTRACTION_RULES_FILE
EXTRACTION_STEP = "Extraction"


class ExtractionRules(BaseModel):
    """The extraction guidance: general lines, candidate criteria, and lines per field key."""

    version: str = Field(min_length=1)
    general: list[RuleLine] = []
    candidates: list[RuleLine] = []
    fields: dict[str, list[RuleLine]] = {}

    def all_rules(self) -> list[RuleLine]:
        """Return every rule line: general, candidate criteria, then each field's."""
        field_rules = [rule for rules in self.fields.values() for rule in rules]
        return [*self.general, *self.candidates, *field_rules]

    def rules_for(self, key: str) -> list[RuleLine]:
        """Return a field's or context attribute's active lines (none if it has no section)."""
        return [rule for rule in self.fields.get(key, []) if rule.is_active]


# ----- Loading -----


def load_extraction_rules(path: Path) -> ExtractionRules:
    """Load `extraction_rules.md` and check it on its own; raise ConfigError on any problem."""
    require_file(path)
    return parse_extraction_rules(path.read_text(encoding="utf-8"))


def parse_extraction_rules(text: str) -> ExtractionRules:
    """Read the file text, run the raw checks, build the model, then run the model checks."""
    document = read_markdown(text)
    raw_problems = (
        find_version_problems(document, FILE_NAME)
        + find_rule_line_problems(document, FILE_NAME)
        + find_section_problems(document)
    )
    if raw_problems:
        raise ConfigError(raw_problems)
    rules = build_extraction_rules(document)
    model_problems = find_step_problems(rules) + find_duplicate_rule_problems(rules)
    if model_problems:
        raise ConfigError(model_problems)
    return rules


def build_extraction_rules(document: RawDocument) -> ExtractionRules:
    """Build the model from raw parts that passed the raw checks."""
    general_lines = [
        build_rule_line(line)
        for section in document.sections
        if section.kind == "general"
        for line in section.lines
    ]
    # Candidate criteria sit under their own heading in the General rules section
    return ExtractionRules(
        version=read_version(document) or "",
        general=[rule for rule in general_lines if rule.heading != CANDIDATE_HEADING],
        candidates=[rule for rule in general_lines if rule.heading == CANDIDATE_HEADING],
        fields={
            section.title.removeprefix(FIELD_PREFIX): [
                build_rule_line(line) for line in section.lines
            ]
            for section in document.field_sections()
        },
    )


# ----- Checks on this file -----


def find_section_problems(document: RawDocument) -> list[str]:
    """Check sections hold only rule lines, field sections are named by key, keys are unique."""
    problems: list[str] = []
    for section in document.sections:
        name = f"{FILE_NAME}: '## {section.title}'"
        if section.kind == "business":
            problems.append(f"{name}: this file has no Business rules section. Remove it.")
        if section.attribute_table is not None or section.tables:
            problems.append(f"{name} has a table; this file holds only rule lines.")
    keys = [section.title.removeprefix(FIELD_PREFIX) for section in document.field_sections()]
    for key in keys:
        problems += find_key_problems(f"{FILE_NAME}: '## {FIELD_PREFIX}{key}'", key)
    problems += [
        f"{FILE_NAME}: '## {FIELD_PREFIX}{key}' is listed twice." for key in repeated(keys)
    ]
    return problems


def find_step_problems(rules: ExtractionRules) -> list[str]:
    """Check every line is tagged [Extraction]: later steps' rules live in business_rules.md."""
    return [
        f"{FILE_NAME}: rule {rule.rule_id} is tagged [{rule.step}]. This file holds only "
        f"[{EXTRACTION_STEP}] lines; move it to {BUSINESS_RULES_FILE}."
        for rule in rules.all_rules()
        if rule.step != EXTRACTION_STEP
    ]


def find_duplicate_rule_problems(rules: ExtractionRules) -> list[str]:
    """Check rule IDs are unique within the file."""
    rule_ids = [rule.rule_id for rule in rules.all_rules()]
    return [f"{FILE_NAME}: rule ID {value} is used twice." for value in repeated(rule_ids)]


# ----- Cross-file checks (called by the config bundle) -----


def find_coverage_problems(
    extraction_rules: ExtractionRules, business_rules: BusinessRules
) -> list[str]:
    """Check each extracted field and context attribute has guidance, and no other key does."""
    owners = [*business_rules.extracted_fields(), *business_rules.context]
    expected_keys = {owner.key for owner in owners}
    # These lines are the model's only instructions for the field
    problems = [
        f"{FILE_NAME}: '{owner.key}' is extracted but has no active [{EXTRACTION_STEP}] line. "
        f"Add a '## {FIELD_PREFIX}{owner.key}' section that says what to copy from the documents."
        for owner in owners
        if not extraction_rules.rules_for(owner.key)
    ]
    problems += [
        f"{FILE_NAME}: '## {FIELD_PREFIX}{key}' is not an extracted field or context attribute "
        f"in {BUSINESS_RULES_FILE}. Fix the key or remove the section."
        for key in extraction_rules.fields
        if key not in expected_keys
    ]
    return problems


def find_shared_rule_id_problems(
    extraction_rules: ExtractionRules, business_rules: BusinessRules
) -> list[str]:
    """Check no rule ID is used in both files."""
    business_ids = {rule.rule_id for rule in business_rules.all_rules()}
    return [
        f"{FILE_NAME}: rule ID {rule.rule_id} is also used in {BUSINESS_RULES_FILE}. "
        "Give one of them a new ID."
        for rule in extraction_rules.all_rules()
        if rule.rule_id in business_ids
    ]
