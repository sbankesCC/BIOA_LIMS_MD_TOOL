"""Extraction rules tests: the parser on a synthetic file, and the startup checks on the real one.

The synthetic file uses made-up keys and rules only (labeled synthetic). Edits to the real file
are built at run time from the loaded rules, so no client value is written here.
"""

from pathlib import Path

import pytest

from app.config.bundle import ConfigBundle
from app.config.errors import ConfigError
from app.config.extraction_rules import parse_extraction_rules
from tests.conftest import assert_config_error, edit_extraction_rules

# A minimal synthetic extraction rules file: general lines, candidate criteria, two keys
SYNTHETIC_EXTRACTION_RULES = """# Synthetic extraction rules

| Attribute | Value |
|---|---|
| Version | 9.9 |

## How to read this file (prose, not parsed)

- This bullet is prose and is ignored.

## General rules (all fields)

### Rules

- SXG-01 [Extraction] Copy synthetic values as written. (Confirmed; synthetic)
- SXG-02 [Extraction] An open synthetic rule. (Open; synthetic question)

### Candidate criteria

- SXC-01 [Extraction] A synthetic candidate is a made-up material. (Design; synthetic)

## Field: syn_name

### Rules

- SXN-01 [Extraction] The synthetic name, as written. (Confirmed; synthetic)

## Field: syn_context

### Rules

- SXX-01 [Extraction] A synthetic context fact. (Confirmed; synthetic)
"""


# ----- Parser -----


def test_general_lines_and_candidate_criteria_are_kept_apart() -> None:
    """Lines under Candidate criteria are the candidates; the other general lines are general."""
    rules = parse_extraction_rules(SYNTHETIC_EXTRACTION_RULES)
    assert rules.version == "9.9"
    assert [rule.rule_id for rule in rules.general] == ["SXG-01", "SXG-02"]
    assert [rule.rule_id for rule in rules.candidates] == ["SXC-01"]


def test_field_sections_are_keyed_by_field_key() -> None:
    """Each `## Field: <key>` section gives that key's lines."""
    rules = parse_extraction_rules(SYNTHETIC_EXTRACTION_RULES)
    assert list(rules.fields) == ["syn_name", "syn_context"]
    assert [rule.rule_id for rule in rules.rules_for("syn_name")] == ["SXN-01"]
    assert rules.rules_for("no_such_key") == []


def test_open_lines_are_parsed_but_inactive() -> None:
    """An Open line is kept in the model but is not active."""
    rules = parse_extraction_rules(SYNTHETIC_EXTRACTION_RULES)
    assert [rule.is_active for rule in rules.general] == [True, False]


def test_line_for_a_later_step_is_rejected() -> None:
    """Only [Extraction] lines belong in this file."""
    text = SYNTHETIC_EXTRACTION_RULES.replace("SXN-01 [Extraction]", "SXN-01 [Validation]")
    with pytest.raises(ConfigError, match=r"SXN-01 is tagged \[Validation\]"):
        parse_extraction_rules(text)


def test_table_in_this_file_is_rejected() -> None:
    """The file holds only rule lines; a table belongs in business_rules.md."""
    table = "| Entry | Status |\n|---|---|\n| SX-T01 | Confirmed |\n"
    text = SYNTHETIC_EXTRACTION_RULES.replace(
        "### Rules\n\n- SXN-01", f"{table}\n### Rules\n\n- SXN-01"
    )
    with pytest.raises(ConfigError, match="holds only rule lines"):
        parse_extraction_rules(text)


def test_field_section_named_twice_is_rejected() -> None:
    """Each key has one section."""
    text = SYNTHETIC_EXTRACTION_RULES.replace("## Field: syn_context", "## Field: syn_name")
    with pytest.raises(ConfigError, match="'## Field: syn_name' is listed twice"):
        parse_extraction_rules(text)


# ----- Startup checks against business_rules.md -----


def test_real_file_covers_every_extracted_field_and_context_attribute(
    bundle: ConfigBundle,
) -> None:
    """Every extracted field and context attribute has active guidance, and nothing else does."""
    owners = [*bundle.business_rules.extracted_fields(), *bundle.business_rules.context]
    assert sorted(bundle.extraction_rules.fields) == sorted(owner.key for owner in owners)
    assert all(bundle.extraction_rules.rules_for(owner.key) for owner in owners)


def test_extracted_field_without_guidance_is_reported(
    config_copy: Path, bundle: ConfigBundle
) -> None:
    """A field the model extracts needs an active line: it is the model's only instruction."""
    key = bundle.business_rules.extracted_fields()[0].key
    # Renaming the section leaves the field with no guidance at all
    edit_extraction_rules(config_copy, f"## Field: {key}\n", "## Field: synthetic_other\n")
    assert_config_error(config_copy, f"'{key}' is extracted but has no active [Extraction] line")


def test_section_for_an_unknown_key_is_reported(config_copy: Path, bundle: ConfigBundle) -> None:
    """A section must name an extracted field or a context attribute of business_rules.md."""
    key = bundle.business_rules.extracted_fields()[0].key
    edit_extraction_rules(config_copy, f"## Field: {key}\n", "## Field: synthetic_unknown\n")
    assert_config_error(config_copy, "'## Field: synthetic_unknown' is not an extracted field")


def test_rule_id_used_in_both_files_is_reported(config_copy: Path, bundle: ConfigBundle) -> None:
    """Rule IDs are unique across extraction_rules.md and business_rules.md."""
    business_id = bundle.business_rules.all_rules()[0].rule_id
    extraction_id = bundle.extraction_rules.general[0].rule_id
    edit_extraction_rules(config_copy, f"- {extraction_id} [", f"- {business_id} [")
    assert_config_error(config_copy, f"rule ID {business_id} is also used in")


def test_missing_extraction_rules_file_stops_loading(config_copy: Path) -> None:
    """Without extraction_rules.md the config does not load."""
    (config_copy / "extraction_rules.md").unlink()
    assert_config_error(config_copy, "extraction_rules.md: file not found")
