"""Prompt templates (`prompts/*.md`): header line with name, version and status; `{placeholders}`.

The placeholder names are the code's side of the contract: the prompt builder fills exactly these.
"""

import re
from pathlib import Path

from pydantic import BaseModel

from app.config.errors import ConfigError, require_file

FOLDER_NAME = "prompts"

# Each prompt the code uses, with the placeholders the prompt builder fills in
EXPECTED_PLACEHOLDERS: dict[str, set[str]] = {
    "extraction": {"field_section", "reextraction_section", "chunks"},
    "extraction_verification": {"chunks", "citation_results", "records", "excluded_items"},
    "duplicate_judge": {"record", "candidates"},
}

HEADER_PATTERN = re.compile(
    r"^<!--\s*prompt:\s*(?P<name>[a-z_]+)\s*\|\s*version:\s*(?P<version>[^|\s]+)\s*"
    r"\|\s*status:\s*(?P<status>[^|]+?)\s*-->$"
)
HTML_COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
PLACEHOLDER_PATTERN = re.compile(r"\{([a-z_]+)\}")


class PromptTemplate(BaseModel):
    """One prompt file: its name, version, status and full text (comments included)."""

    name: str
    version: str
    status: str
    text: str


def load_prompts(folder: Path) -> dict[str, PromptTemplate]:
    """Load every prompt the code uses and check its header and placeholders."""
    prompts: dict[str, PromptTemplate] = {}
    problems: list[str] = []
    for name, expected in EXPECTED_PLACEHOLDERS.items():
        path = folder / f"{name}.md"
        require_file(path)
        prompt = read_prompt(path, problems)
        if prompt is None:
            continue
        problems.extend(find_placeholder_problems(prompt, expected))
        prompts[name] = prompt
    if problems:
        raise ConfigError(problems)
    return prompts


def read_prompt(path: Path, problems: list[str]) -> PromptTemplate | None:
    """Read a prompt file and parse its header line; add a problem if the header is wrong."""
    text = path.read_text(encoding="utf-8")
    first_line = text.splitlines()[0].strip() if text else ""
    match = HEADER_PATTERN.match(first_line)
    file_label = f"{FOLDER_NAME}/{path.name}"
    if match is None:
        problems.append(
            f"{file_label}: the first line must be "
            "'<!-- prompt: <name> | version: <version> | status: <status> -->'."
        )
        return None
    # The header name must match the file so traces name the right template
    if match["name"] != path.stem:
        problems.append(f"{file_label}: the header names '{match['name']}', not '{path.stem}'.")
    return PromptTemplate(
        name=path.stem, version=match["version"], status=match["status"], text=text
    )


def find_placeholder_problems(prompt: PromptTemplate, expected: set[str]) -> list[str]:
    """Compare the placeholders outside HTML comments with the ones the code fills."""
    body = HTML_COMMENT_PATTERN.sub("", prompt.text)
    found = set(PLACEHOLDER_PATTERN.findall(body))
    file_label = f"{FOLDER_NAME}/{prompt.name}.md"
    problems = [
        f"{file_label}: placeholder {{{name}}} is missing." for name in sorted(expected - found)
    ]
    problems.extend(
        f"{file_label}: placeholder {{{name}}} is unknown; the code cannot fill it."
        for name in sorted(found - expected)
    )
    return problems
