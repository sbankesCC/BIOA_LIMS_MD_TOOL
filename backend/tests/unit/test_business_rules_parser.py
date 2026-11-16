"""Business rules parser tests: the real file, and a small synthetic file for the grammar details.

The synthetic file uses made-up fields and values only (labeled synthetic).
"""

import pytest

from app.config.bundle import ConfigBundle
from app.config.business_rules import OneOfGroup
from app.config.business_rules_checks import parse_business_rules

# A minimal synthetic business rules file: two fields, one context attribute, one group
SYNTHETIC_RULES = """# Synthetic business rules

| Attribute | Value |
|---|---|
| Version | 9.9 |

## How to read this file (prose, not parsed)

- This bullet is prose and is ignored.

## General rules (all fields)

### Rules

- SG-01 [Extraction] Copy synthetic values as written. (Confirmed; synthetic)
- SG-02 [Extraction] An open synthetic rule. (Open; synthetic question)

### Synthetic table

| Entry | Match type | Lookup value | Status |
|---|---|---|---|
| ST-01 | phrase | syn-a | Confirmed |
| ST-02 | phrase | syn-b | Open (waiting on synthetic answer) |

## Field: Synthetic Name

| Attribute | Value |
|---|---|
| Key | syn_name |
| Loader column | Synthetic Name |
| Role | generated |
| Requirement | required |
| Type | text |
| Max length | 40 |
| Record name | yes |
| Sent to duplicate judge | yes |

### Rules

- SN-01 [Extraction] The synthetic name (e.g., "Syn A"), as written. (Assumption; SYN-1: note, BR-0)

## Field: Synthetic Amount

| Attribute | Value |
|---|---|
| Key | syn_amount |
| Loader column | Synthetic Amount |
| Role | extracted |
| Requirement | conditional (syn_group) |
| Type | decimal |
| Multi-value separator | ", " |

### Rules

- SA-01 [Extraction] The synthetic amount. (Design; synthetic)

## Field: syn_context

| Attribute | Value |
|---|---|
| Key | syn_context |
| Loader column | none |
| Role | context |
| Requirement | optional |
| Type | text |
| Drives | syn_amount |

### Rules

- SX-01 [Extraction] A synthetic context fact. (Confirmed; synthetic)

## Business rules (across fields)

### Naming rules

- SNM-01 [Naming] Name synthetic things plainly. (Design; synthetic)

### Condition groups

| Group | Rule | Fields | Issue code | Status |
|---|---|---|---|---|
| syn_group | one_of | syn_amount + syn_name; syn_amount | CONDITION_UNMET | Design |

## Change log

| Version | Date | Change |
|---|---|---|
| 0.1 | 2000-01-01 | Not parsed |
"""


def test_real_file_has_the_redesigned_field_set(bundle: ConfigBundle) -> None:
    """The real file holds 22 loader fields, 13 extracted, 4 derived and 2 context attributes."""
    rules = bundle.business_rules
    assert len(rules.fields) == 22
    assert len(rules.extracted_fields()) == 13
    assert len(rules.derived_fields()) == 4
    assert len(rules.context_fields()) == 2
    assert all(
        attribute.drives in {field.key for field in rules.fields} for attribute in rules.context
    )
    assert rules.record_name_field().role == "generated"
    assert len(rules.condition_groups) == 2


def test_real_file_open_rules_are_parsed_but_inactive(bundle: ConfigBundle) -> None:
    """Open lines are read (so they can be listed) but rules_for leaves them out."""
    rules = bundle.business_rules
    open_plausibility = rules.rules_for("Plausibility", active_only=False)
    assert open_plausibility
    assert all(not rule.is_active for rule in open_plausibility)
    assert rules.rules_for("Plausibility") == []


def test_version_comes_from_the_first_table() -> None:
    """The Version row of the first table is the file's version, not the change log's."""
    assert parse_business_rules(SYNTHETIC_RULES).version == "9.9"


def test_only_parsed_sections_are_read() -> None:
    """Prose sections (How to read, Change log) are not read as rules or fields."""
    rules = parse_business_rules(SYNTHETIC_RULES)
    assert [field.key for field in rules.fields] == ["syn_name", "syn_amount"]
    assert [rule.rule_id for rule in rules.general.rules] == ["SG-01", "SG-02"]


def test_status_is_the_first_word_and_the_rest_is_a_note() -> None:
    """A rule's status is the first word in its last parentheses; the rest is its note."""
    rule = parse_business_rules(SYNTHETIC_RULES).rules_for("Extraction", "syn_name")[0]
    assert rule.status == "Assumption"
    assert rule.note == "SYN-1: note, BR-0"
    assert rule.text == 'The synthetic name (e.g., "Syn A"), as written.'


def test_open_rule_lines_are_inactive() -> None:
    """An Open rule line is kept but not returned by rules_for."""
    rules = parse_business_rules(SYNTHETIC_RULES)
    active = [rule.rule_id for rule in rules.rules_for("Extraction")]
    every = [rule.rule_id for rule in rules.rules_for("Extraction", active_only=False)]
    assert "SG-02" not in active
    assert "SG-02" in every


def test_open_table_rows_are_inactive() -> None:
    """A table row whose Status starts with Open is left out of active_rows; the note is ignored."""
    table = parse_business_rules(SYNTHETIC_RULES).table("general", "Synthetic table")
    assert [row["Entry"] for row in table.rows] == ["ST-01", "ST-02"]
    assert [row["Entry"] for row in table.active_rows()] == ["ST-01"]


def test_attributes_are_read_into_the_field() -> None:
    """Requirement group, separator, flags and max length come from the attribute table."""
    rules = parse_business_rules(SYNTHETIC_RULES)
    name, amount = rules.fields
    assert (name.is_record_name, name.sent_to_duplicate_judge, name.max_length) == (True, True, 40)
    assert (amount.requirement, amount.condition_group) == ("conditional", "syn_group")
    assert (amount.separator, amount.multi_value) == (", ", True)
    assert name.is_extracted and amount.is_extracted


def test_escaped_bar_stays_inside_its_cell() -> None:
    """An escaped bar in a table cell is a literal bar, not a cell boundary."""
    text = SYNTHETIC_RULES.replace(
        '| Multi-value separator | ", " |', '| Multi-value separator | "\\|" |'
    )
    amount = parse_business_rules(text).fields[1]
    assert amount.separator == "|"


def test_context_attributes_are_kept_out_of_the_loader_fields() -> None:
    """A context attribute has no column and is not one of the loader fields."""
    rules = parse_business_rules(SYNTHETIC_RULES)
    assert [attribute.key for attribute in rules.context_fields()] == ["syn_context"]
    assert rules.context[0].drives == "syn_amount"
    assert rules.columns() == ["Synthetic Name", "Synthetic Amount"]


def test_rule_lines_keep_their_heading() -> None:
    """Business rule lines remember the `###` heading they sit under."""
    rule = parse_business_rules(SYNTHETIC_RULES).rules_for("Naming")[0]
    assert (rule.rule_id, rule.heading) == ("SNM-01", "Naming rules")


def test_condition_groups_come_from_their_table() -> None:
    """`;` separates the options of a one_of group and `+` joins the fields of an option."""
    group = parse_business_rules(SYNTHETIC_RULES).condition_groups["syn_group"]
    assert isinstance(group, OneOfGroup)
    assert group.options == [["syn_amount", "syn_name"], ["syn_amount"]]


def test_unknown_table_heading_names_the_problem() -> None:
    """Asking for a table that does not exist raises a plain KeyError."""
    with pytest.raises(KeyError, match="has no table"):
        parse_business_rules(SYNTHETIC_RULES).table("business", "No such table")
