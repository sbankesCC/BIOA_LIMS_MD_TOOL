"""Business rules startup checks: each test breaks one thing in a copy and loading names it.

Edits are built at run time from the loaded rules, so no client value is written in this file.
"""

from pathlib import Path

from openpyxl import load_workbook

from app.config.bundle import ConfigBundle
from app.config.business_rules import (
    ENTRY_COLUMN,
    LOOKUP_VALUE_COLUMN,
    BusinessRules,
    RuleTable,
    is_blank_cell,
)
from tests.conftest import assert_config_error, edit_business_rules

BUSINESS_RULES = "business_rules.md"


def set_attribute(config_dir: Path, key: str, attribute: str, value: str | None) -> None:
    """Set (or remove, with None) one attribute row in the section whose Key is `key`."""
    path = config_dir / BUSINESS_RULES
    lines = path.read_text(encoding="utf-8").split("\n")
    start = lines.index(f"| Key | {key} |")
    # Attribute rows run from the Key row to the end of the table
    end = next(index for index in range(start, len(lines)) if not lines[index].startswith("|"))
    new_row = None if value is None else f"| {attribute} | {value} |"
    rows = [index for index in range(start, end) if lines[index].startswith(f"| {attribute} |")]
    if rows and new_row is None:
        del lines[rows[0]]
    elif rows and new_row is not None:
        lines[rows[0]] = new_row
    elif new_row is not None:
        lines.insert(end, new_row)
    path.write_text("\n".join(lines), encoding="utf-8")


def table_row_text(table: RuleTable, row: dict[str, str]) -> str:
    """Return a table row as it is written in the Markdown file."""
    # An empty cell is written as a single space between bars
    cells = [f" {row[column]} " if row[column] else " " for column in table.columns]
    return "|" + "|".join(cells) + "|"


def first_rule_id(rules: BusinessRules) -> str:
    """Return the ID of the first rule line in the file."""
    return rules.all_rules()[0].rule_id


def first_conditional_key(rules: BusinessRules) -> str:
    """Return the key of the first field whose requirement is conditional."""
    return next(field.key for field in rules.fields if field.requirement == "conditional")


# ----- Missing file and version -----


def test_missing_business_rules_file_stops_loading(config_copy: Path) -> None:
    """Without business_rules.md the config does not load; there is no fallback."""
    (config_copy / BUSINESS_RULES).unlink()
    assert_config_error(config_copy, f"{BUSINESS_RULES}: file not found")


def test_missing_version_is_reported(config_copy: Path, bundle: ConfigBundle) -> None:
    """The first table must have a Version row."""
    version = bundle.business_rules.version
    edit_business_rules(config_copy, f"| Version | {version} |", "| Edition | 1 |")
    assert_config_error(config_copy, "needs a 'Version' row")


# ----- Attribute tables -----


def test_unknown_role_is_reported(config_copy: Path, bundle: ConfigBundle) -> None:
    """A role outside the allowed set is rejected."""
    set_attribute(config_copy, bundle.business_rules.fields[0].key, "Role", "guess")
    assert_config_error(config_copy, "'Role' is 'guess'")


def test_missing_required_attribute_is_reported(config_copy: Path, bundle: ConfigBundle) -> None:
    """Each field needs the five required attributes."""
    set_attribute(config_copy, bundle.business_rules.fields[0].key, "Type", None)
    assert_config_error(config_copy, "is missing the attribute 'Type'")


def test_unknown_attribute_is_reported(config_copy: Path, bundle: ConfigBundle) -> None:
    """An attribute key the grammar does not know is rejected."""
    set_attribute(config_copy, bundle.business_rules.fields[0].key, "Colour", "blue")
    assert_config_error(config_copy, "unknown attribute 'Colour'")


def test_bad_max_length_is_reported(config_copy: Path, bundle: ConfigBundle) -> None:
    """Max length must be a whole number above 0."""
    set_attribute(config_copy, bundle.business_rules.fields[0].key, "Max length", "0")
    assert_config_error(config_copy, "'Max length' must be a whole number above 0")


def test_context_attribute_with_a_column_is_reported(
    config_copy: Path, bundle: ConfigBundle
) -> None:
    """A context attribute is never exported, so its loader column must be none."""
    set_attribute(config_copy, bundle.business_rules.context[0].key, "Loader column", "Synthetic")
    assert_config_error(config_copy, "its 'Loader column' must be none")


# ----- Rule lines and tables -----


def test_bullet_that_is_not_a_rule_line_is_reported(config_copy: Path) -> None:
    """Every bullet in a parsed section must be a rule line."""
    edit_business_rules(config_copy, "### Rules\n", "### Rules\n\n- a synthetic note\n", count=None)
    assert_config_error(config_copy, "is not a rule line")


def test_unknown_step_tag_is_reported(config_copy: Path, bundle: ConfigBundle) -> None:
    """A rule line's step tag must be one of the seven steps."""
    rule = bundle.business_rules.all_rules()[0]
    edit_business_rules(config_copy, f"- {rule.rule_id} [{rule.step}]", f"- {rule.rule_id} [Guess]")
    assert_config_error(config_copy, "'step' is 'Guess'")


def test_unknown_rule_status_is_reported(config_copy: Path, bundle: ConfigBundle) -> None:
    """A rule line's status must start with one of the four labels."""
    rule = bundle.business_rules.all_rules()[0]
    line = f"({rule.status}; {rule.note})"
    edit_business_rules(config_copy, line, f"(Maybe; {rule.note})", count=None)
    assert_config_error(config_copy, "'status' is 'Maybe'")


def test_table_row_with_wrong_cell_count_is_reported(
    config_copy: Path, bundle: ConfigBundle
) -> None:
    """Every table row has one cell per column."""
    table = bundle.business_rules.business.tables[0]
    row = table_row_text(table, table.rows[0])
    edit_business_rules(config_copy, row, row + " extra |")
    assert_config_error(config_copy, "a row has")


def test_unknown_status_cell_is_reported(config_copy: Path, bundle: ConfigBundle) -> None:
    """A table Status cell must start with one of the four labels."""
    table = bundle.business_rules.business.tables[0]
    row = table.rows[0]
    changed = {**row, "Status": "Maybe"}
    edit_business_rules(config_copy, table_row_text(table, row), table_row_text(table, changed))
    assert_config_error(config_copy, "'Status' is 'Maybe'")


def test_unknown_condition_group_rule_is_reported(config_copy: Path, bundle: ConfigBundle) -> None:
    """A condition group's Rule must be one_of or both_or_neither."""
    table = bundle.business_rules.table("business", "Condition groups")
    row = table.rows[0]
    changed = {**row, "Rule": "all_or_none"}
    edit_business_rules(config_copy, table_row_text(table, row), table_row_text(table, changed))
    assert_config_error(config_copy, "'Rule' is 'all_or_none'")


# ----- Unique IDs -----


def test_duplicate_rule_id_is_reported(config_copy: Path, bundle: ConfigBundle) -> None:
    """Rule IDs are unique across the file."""
    rules = bundle.business_rules.all_rules()
    edit_business_rules(config_copy, f"- {rules[1].rule_id} [", f"- {rules[0].rule_id} [")
    assert_config_error(config_copy, f"rule ID {rules[0].rule_id} is used twice")


def test_duplicate_table_entry_is_reported(config_copy: Path, bundle: ConfigBundle) -> None:
    """Table entry IDs are unique across the file."""
    table = next(
        table
        for owner in bundle.business_rules.owners()
        for table in owner.tables
        if ENTRY_COLUMN in table.columns and len(table.rows) >= 2
    )
    first, second = table.rows[0][ENTRY_COLUMN], table.rows[1][ENTRY_COLUMN]
    edit_business_rules(config_copy, f"| {second} |", f"| {first} |")
    assert_config_error(config_copy, f"table entry {first} is used twice")


def test_duplicate_field_key_is_reported(config_copy: Path, bundle: ConfigBundle) -> None:
    """Field keys are unique."""
    fields = bundle.business_rules.fields
    edit_business_rules(config_copy, f"| Key | {fields[1].key} |", f"| Key | {fields[0].key} |")
    assert_config_error(config_copy, f"field key '{fields[0].key}' is used twice")


# ----- Record name and extraction lines -----


def test_no_record_name_field_is_reported(config_copy: Path) -> None:
    """Exactly one field must be the record name; zero is rejected."""
    edit_business_rules(config_copy, "| Record name | yes |\n", "")
    assert_config_error(config_copy, "exactly one field must have 'Record name | yes', but 0 do")


def test_two_record_name_fields_are_reported(config_copy: Path, bundle: ConfigBundle) -> None:
    """Exactly one field must be the record name; two are rejected."""
    other = next(field for field in bundle.business_rules.fields if not field.is_record_name)
    set_attribute(config_copy, other.key, "Record name", "yes")
    assert_config_error(config_copy, "but 2 do")


def test_record_name_not_sent_to_judge_is_reported(config_copy: Path, bundle: ConfigBundle) -> None:
    """The record name field must also be sent to the duplicate judge."""
    name_key = bundle.business_rules.record_name_field().key
    set_attribute(config_copy, name_key, "Sent to duplicate judge", None)
    assert_config_error(config_copy, "is not sent to the duplicate judge")


def test_extracted_field_without_extraction_line_is_reported(
    config_copy: Path, bundle: ConfigBundle
) -> None:
    """A field the model extracts needs an active [Extraction] line: its only instruction."""
    field = bundle.business_rules.extracted_fields()[0]
    for rule in bundle.business_rules.rules_for("Extraction", field.key):
        edit_business_rules(
            config_copy, f"- {rule.rule_id} [Extraction]", f"- {rule.rule_id} [Assembly]"
        )
    assert_config_error(config_copy, f"'{field.key}' is extracted but has no active [Extraction]")


# ----- References between parts -----


def test_drives_naming_an_unknown_field_is_reported(
    config_copy: Path, bundle: ConfigBundle
) -> None:
    """A context attribute's Drives value must be a loader field key."""
    set_attribute(config_copy, bundle.business_rules.context[0].key, "Drives", "no_such_field")
    assert_config_error(config_copy, "drives 'no_such_field'")


def test_condition_group_with_unknown_field_is_reported(
    config_copy: Path, bundle: ConfigBundle
) -> None:
    """A condition group naming a field that does not exist is rejected."""
    table = bundle.business_rules.table("business", "Condition groups")
    row = table.rows[-1]
    changed = {**row, "Fields": row["Fields"] + "; no_such_field"}
    edit_business_rules(config_copy, table_row_text(table, row), table_row_text(table, changed))
    assert_config_error(config_copy, "unknown field 'no_such_field'")


def test_conditional_field_without_a_group_is_reported(
    config_copy: Path, bundle: ConfigBundle
) -> None:
    """A conditional field must name an active condition group."""
    set_attribute(
        config_copy, first_conditional_key(bundle.business_rules), "Requirement", "conditional"
    )
    assert_config_error(config_copy, "is conditional but names no active condition group")


# ----- Cross-file checks -----


def test_missing_lookup_list_is_reported(config_copy: Path, bundle: ConfigBundle) -> None:
    """Every lookup list a field names must be a sheet of the lookup workbook."""
    field = next(field for field in bundle.business_rules.fields if field.lookup_sheet)
    set_attribute(config_copy, field.key, "Lookup list", "Synthetic Missing List")
    assert_config_error(config_copy, "the sheet 'Synthetic Missing List'")


def test_default_not_on_lookup_list_is_reported(config_copy: Path, bundle: ConfigBundle) -> None:
    """A lookup field's default must be on its list."""
    field = next(f for f in bundle.business_rules.fields if f.lookup_sheet and f.default)
    set_attribute(config_copy, field.key, "Default", "synthetic-not-a-value")
    assert_config_error(config_copy, "'Default' value 'synthetic-not-a-value'")


def test_translation_target_not_on_lookup_list_is_reported(
    config_copy: Path, bundle: ConfigBundle
) -> None:
    """A translation table's Lookup value must be on the field's list."""
    table, row = next(
        (table, row)
        for field in bundle.business_rules.fields
        for table in field.tables
        if LOOKUP_VALUE_COLUMN in table.columns
        for row in table.rows
        if not is_blank_cell(row[LOOKUP_VALUE_COLUMN])
    )
    changed = {**row, LOOKUP_VALUE_COLUMN: "synthetic-not-a-value"}
    edit_business_rules(config_copy, table_row_text(table, row), table_row_text(table, changed))
    assert_config_error(config_copy, "value 'synthetic-not-a-value' is not on its lookup list")


def test_table_output_not_on_lookup_list_is_reported(
    config_copy: Path, bundle: ConfigBundle
) -> None:
    """A table column named after a lookup field holds only that field's list values."""
    rules = bundle.business_rules
    lookup_columns = [field.column for field in rules.fields if field.lookup_sheet]
    table = rules.business.tables[0]
    column = next(column for column in table.columns if column in lookup_columns)
    row = next(row for row in table.rows if not is_blank_cell(row[column]) and row[column] != "any")
    changed = {**row, column: "synthetic-not-a-value"}
    edit_business_rules(config_copy, table_row_text(table, row), table_row_text(table, changed))
    assert_config_error(config_copy, "value 'synthetic-not-a-value' is not on its lookup list")


def test_template_headers_must_equal_loader_columns(config_copy: Path) -> None:
    """The DFD template headers must equal the loader columns, in order."""
    path = config_copy / "dfd_template.xlsx"
    workbook = load_workbook(path)
    workbook["Sheet1"]["A1"] = "Synthetic Header"
    workbook.save(path)
    assert_config_error(config_copy, "the headers do not match the loader columns")
