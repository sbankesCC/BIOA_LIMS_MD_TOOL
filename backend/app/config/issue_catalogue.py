"""Issue catalogue (`issue_catalogue.yaml`): every issue code with its severity and message."""

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.config.errors import ConfigError, parse_model, read_yaml

FILE_NAME = "issue_catalogue.yaml"

# Placeholders the code knows how to fill in a message; anything else would show as raw braces
MESSAGE_PLACEHOLDERS = {
    "field",
    "value",
    "original",
    "max_length",
    "file",
    "items",
    "count",
    "other",
}
PLACEHOLDER_PATTERN = re.compile(r"\{([a-z_]+)\}")
CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")

Severity = Literal["error", "warning", "info"]


class IssueDefinition(BaseModel):
    """One issue code: severity, user message and review flags."""

    model_config = ConfigDict(extra="forbid")

    severity: Severity
    message: str = Field(min_length=1)
    individual_review: bool = False
    note_required: bool = False


class IssueCatalogue(BaseModel):
    """The whole catalogue: record-level and run-level issue codes."""

    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1)
    record_issues: dict[str, IssueDefinition]
    run_issues: dict[str, IssueDefinition]

    def all_codes(self) -> set[str]:
        """Return every issue code, record-level and run-level."""
        return set(self.record_issues) | set(self.run_issues)


def load_issue_catalogue(path: Path) -> IssueCatalogue:
    """Load `issue_catalogue.yaml` and check codes, flags and messages."""
    catalogue = parse_model(IssueCatalogue, read_yaml(path), FILE_NAME)
    problems: list[str] = []
    # A code must mean one thing, so it cannot be both record-level and run-level
    for code in sorted(set(catalogue.record_issues) & set(catalogue.run_issues)):
        problems.append(f"{FILE_NAME}: code {code} is in both record_issues and run_issues.")
    all_definitions = catalogue.record_issues | catalogue.run_issues
    for code, definition in all_definitions.items():
        problems.extend(find_definition_problems(code, definition))
    if problems:
        raise ConfigError(problems)
    return catalogue


def find_definition_problems(code: str, definition: IssueDefinition) -> list[str]:
    """Check one issue code's name, flags and message placeholders."""
    problems: list[str] = []
    if not CODE_PATTERN.match(code):
        problems.append(f"{FILE_NAME}: code '{code}' must be UPPER_SNAKE_CASE.")
    # Only warnings can be accepted, so review flags only make sense on warnings
    if definition.individual_review and definition.severity != "warning":
        problems.append(f"{FILE_NAME}: {code} has individual_review but is not a warning.")
    if definition.note_required and not definition.individual_review:
        problems.append(f"{FILE_NAME}: {code} has note_required without individual_review.")
    for placeholder in PLACEHOLDER_PATTERN.findall(definition.message):
        if placeholder not in MESSAGE_PLACEHOLDERS:
            problems.append(
                f"{FILE_NAME}: {code} message uses {{{placeholder}}}, which the code cannot fill."
            )
    return problems


def fill_message(message: str, values: Mapping[str, str]) -> str:
    """Fill the `{placeholder}`s of a catalogue message; ones without a value stay as written."""

    def replace(match: re.Match[str]) -> str:
        """Return the value for one placeholder, or the placeholder itself."""
        return values.get(match.group(1), match.group(0))

    return PLACEHOLDER_PATTERN.sub(replace, message)
