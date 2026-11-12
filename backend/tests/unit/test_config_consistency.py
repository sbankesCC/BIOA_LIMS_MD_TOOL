"""Config consistency: business rules and seed lookup lists against BioA's source workbook.

The source workbook (Data info + List Values sheets) holds BioA's original field definitions.
`business_rules.md` differs from it on purpose in a few places. Every allowed difference below
cites its rule ID in `business_rules.md` (or the decision it comes from), and each one must be
used: an unused one means the config or the workbook changed and the list needs a review.
"""

import re
from dataclasses import dataclass, field
from typing import Any

import pytest
from openpyxl import load_workbook

from app.config.bundle import ConfigBundle
from app.config.business_rules import (
    LOOKUP_VALUE_COLUMN,
    BusinessRules,
    FieldDefinition,
    fields_in_group,
    split_list_cell,
)
from app.config.business_rules_checks import all_tables
from tests.conftest import SOURCE_WORKBOOK

# Allowed differences between business_rules.md and the source workbook, with their sources
ALLOWED_DIFFERENCES = {
    "source_fields_removed": (
        "Three source fields are not loader fields: container size and unit come from the "
        "Container Type record (CO-06, D-45) and the parameters field was dropped (D-38)."
    ),
    "expiry_fields_added": (
        "The three expiry fields are in BioA's updated field list but not in the source "
        "workbook; role blank_for_now, exported blank (EX-01 to EX-03, BR-7)."
    ),
    "record_name_is_generated": (
        "The record name is extracted as written, then the Naming step suggests it (CT-02)."
    ),
    "derived_from_other_values": (
        "Consumable Class, Critical, Approval Type and Worksheet Template are derived by "
        "Assembly from other values (CC-01, CR-01, AT-01, WT-01 to WT-03)."
    ),
    "seeded_from_business_rules": (
        "Approval Type and Worksheet Template have no source list; they are seeded with the "
        "values the business rules tables name (AT-01, AT-02, WT-01, WT-02; user decision 3)."
    ),
    "tracking_method_codes": (
        "Container Tracking Method holds the codes the translation table maps the source's "
        "displayed values to, default included (TM-02 to TM-04)."
    ),
    "container_type_required": "Container Type is required (CO-05).",
    "mandatory_in_condition_group_is_conditional": (
        "Data info marks the amount, amount unit and container count fields Mandatory, but its "
        "note says amount + unit OR containers is mandatory: read as conditional (COND-01)."
    ),
    "blank_lookup_entry_removed": (
        "A blank entry in a List Values column is not a value; it was left out of the seed."
    ),
    "lookup_value_whitespace_trimmed": (
        "A leading line break in a List Values cell is a copy artefact; it was removed."
    ),
}

# Source workbook layout
DATA_INFO_SHEET = "Data info"
LIST_VALUES_SHEET = "List Values"
FIELDS_TO_ADD_MARKER = "Fields to add:"
DEFAULT_NOTE_PATTERN = re.compile(r"Default\s*=\s*(.+)$")
DATA_TYPES = {"Char": "text", "Decimal": "decimal", "Number": "integer"}

# Source rows that are not loader fields any more (see source_fields_removed)
REMOVED_SOURCE_FIELD_COUNT = 3

# The one field CO-05 makes required although the source marks it optional
REQUIRED_BY_RULE = {"container_type"}


@dataclass
class SourceField:
    """One field row from the Data info sheet, with the 'Fields to add' position."""

    column: str
    field_type: str
    data_type: str
    mandatory_optional: str
    field_input: str
    character_limit: int | None
    notes: str | None
    is_field_to_add: bool


@dataclass
class Comparison:
    """Differences found, and which allowed differences were used to explain others."""

    differences: list[str] = field(default_factory=list)
    used_rules: set[str] = field(default_factory=set)


def read_source_fields() -> list[SourceField]:
    """Read the Data info sheet into field rows, in order."""
    worksheet = load_workbook(SOURCE_WORKBOOK, data_only=True)[DATA_INFO_SHEET]
    rows = list(worksheet.iter_rows(min_row=2, values_only=True))
    fields: list[SourceField] = []
    is_field_to_add = False
    for row in rows:
        if row[0] is None:
            continue
        # The marker row splits current fields from fields BioA wants to add
        if str(row[0]).strip() == FIELDS_TO_ADD_MARKER:
            is_field_to_add = True
            continue
        fields.append(source_field_from_row(row, is_field_to_add))
    return fields


def source_field_from_row(row: tuple[Any, ...], is_field_to_add: bool) -> SourceField:
    """Build a SourceField from one Data info row."""
    return SourceField(
        column=str(row[0]),
        field_type=str(row[1]),
        data_type=str(row[2]),
        mandatory_optional=str(row[4]),
        field_input=str(row[5]),
        character_limit=row[6] if isinstance(row[6], int) else None,
        notes=None if row[7] is None else str(row[7]),
        is_field_to_add=is_field_to_add,
    )


def read_source_lists() -> dict[str, list[str]]:
    """Read the List Values sheet: one column per lookup list, header in row 1."""
    worksheet = load_workbook(SOURCE_WORKBOOK, data_only=True)[LIST_VALUES_SHEET]
    columns = list(worksheet.iter_cols(values_only=True))
    lists: dict[str, list[str]] = {}
    for column in columns:
        if column[0] is None:
            continue
        lists[str(column[0])] = [str(cell) for cell in column[1:] if cell is not None]
    return lists


def translation_map(rule: FieldDefinition) -> dict[str, str]:
    """Return a field's translation table as document wording → lookup value."""
    mapping: dict[str, str] = {}
    for table in rule.tables:
        for row in table.active_rows():
            for wording in split_list_cell(row.get("Document wording", "")):
                mapping[wording] = row.get(LOOKUP_VALUE_COLUMN, "")
    return mapping


def expected_role(source: SourceField, rule: FieldDefinition, comparison: Comparison) -> str:
    """Return the role the source implies, unless an allowed difference explains the rule's."""
    if source.field_type == "System Generated":
        return "system"
    if rule.role == "generated" and rule.is_record_name:
        comparison.used_rules.add("record_name_is_generated")
        return rule.role
    if rule.role == "derived":
        comparison.used_rules.add("derived_from_other_values")
        return rule.role
    return "extracted"


def expected_requirement(
    source: SourceField, grouped: set[str], rule: FieldDefinition, comparison: Comparison
) -> str:
    """Return the requirement the source implies, after the allowed differences."""
    if source.mandatory_optional == "Mandatory" and rule.key in grouped:
        comparison.used_rules.add("mandatory_in_condition_group_is_conditional")
        return "conditional"
    if source.mandatory_optional == "Mandatory":
        return "required"
    if rule.key in REQUIRED_BY_RULE:
        comparison.used_rules.add("container_type_required")
        return "required"
    return "optional"


def expected_type(source: SourceField) -> str:
    """Return the field type: Boolean input wins, otherwise the Data Type column."""
    if source.field_input == "Boolean":
        return "boolean"
    return DATA_TYPES[source.data_type]


def expected_default(
    source: SourceField, rule: FieldDefinition, comparison: Comparison
) -> str | None:
    """Return the default from a 'Default = X' note, translated to a code if the table says so."""
    match = DEFAULT_NOTE_PATTERN.search(source.notes or "")
    default = match.group(1).strip() if match else None
    translated = translation_map(rule).get(default or "")
    if translated:
        comparison.used_rules.add("tracking_method_codes")
        return translated
    return default


def compare_field(
    source: SourceField, rule: FieldDefinition, grouped: set[str], comparison: Comparison
) -> None:
    """Compare one source row with its field definition, recording each difference."""
    checks: dict[str, tuple[object, object]] = {
        "role": (expected_role(source, rule, comparison), rule.role),
        "type": (expected_type(source), rule.type),
        "max_length": (source.character_limit, rule.max_length),
        "has lookup list": (source.field_input == "List", rule.lookup_sheet == rule.column),
        "default": (expected_default(source, rule, comparison), rule.default),
        "requirement": (expected_requirement(source, grouped, rule, comparison), rule.requirement),
    }
    for name, (expected, actual) in checks.items():
        if expected != actual:
            comparison.differences.append(
                f"{rule.column}: {name} is {actual!r}, source gives {expected!r}"
            )


def compare_field_lists(rules: BusinessRules, comparison: Comparison) -> None:
    """Compare which fields exist: removed source rows and added expiry fields are allowed."""
    source_columns = [source.column for source in read_source_fields()]
    removed = [column for column in source_columns if column not in rules.columns()]
    added = [rule for rule in rules.fields if rule.column not in source_columns]
    if len(removed) == REMOVED_SOURCE_FIELD_COUNT:
        comparison.used_rules.add("source_fields_removed")
    else:
        comparison.differences.append(f"{len(removed)} source fields have no field section")
    if added and all(rule.role == "blank_for_now" for rule in added):
        comparison.used_rules.add("expiry_fields_added")
    else:
        comparison.differences.append("fields not in the source must be blank_for_now")


def clean_source_values(source_values: list[str], comparison: Comparison) -> list[str]:
    """Clean the source values by the allowed rules and return them for comparison."""
    cleaned: list[str] = []
    for value in source_values:
        if not value.strip():
            comparison.used_rules.add("blank_lookup_entry_removed")
            continue
        if value != value.strip():
            comparison.used_rules.add("lookup_value_whitespace_trimmed")
        cleaned.append(value.strip())
    return cleaned


def table_cells(rules: BusinessRules) -> set[str]:
    """Return every cell value in the business rules tables (lists split)."""
    return {
        value
        for table in all_tables(rules)
        for row in table.rows
        for cell in row.values()
        for value in split_list_cell(cell)
    }


def compare_sheet(
    sheet_name: str, seed_values: list[str], rules: BusinessRules, comparison: Comparison
) -> None:
    """Compare one seed sheet with its source list, after the allowed differences."""
    source_lists = read_source_lists()
    rule = next((rule for rule in rules.fields if rule.lookup_sheet == sheet_name), None)
    # A sheet with no source list is seeded from the values the business rules name
    if sheet_name not in source_lists and set(seed_values) <= table_cells(rules):
        comparison.used_rules.add("seeded_from_business_rules")
        return
    cleaned = clean_source_values(source_lists.get(sheet_name, []), comparison)
    translations = translation_map(rule) if rule is not None else {}
    if translations and [translations.get(value) for value in cleaned] == seed_values:
        comparison.used_rules.add("tracking_method_codes")
        return
    if cleaned != seed_values:
        comparison.differences.append(f"Lookup sheet '{sheet_name}' differs from List Values")


@pytest.fixture(scope="module")
def field_comparison(bundle: ConfigBundle) -> Comparison:
    """Compare every field definition with its Data info row, and the field lists."""
    rules = bundle.business_rules
    comparison = Comparison()
    grouped = {key for group in rules.condition_groups.values() for key in fields_in_group(group)}
    rules_by_column = {rule.column: rule for rule in rules.fields}
    for source in read_source_fields():
        rule = rules_by_column.get(source.column)
        if rule is not None:
            compare_field(source, rule, grouped, comparison)
    compare_field_lists(rules, comparison)
    return comparison


@pytest.fixture(scope="module")
def lookup_comparison(bundle: ConfigBundle) -> Comparison:
    """Compare every seed lookup sheet with its List Values column."""
    comparison = Comparison()
    for sheet_name, seed_values in bundle.lookup_lists.sheets.items():
        compare_sheet(sheet_name, seed_values, bundle.business_rules, comparison)
    return comparison


def test_field_order_matches_source(bundle: ConfigBundle) -> None:
    """The fields both files share are in the same order; added fields come last."""
    columns = bundle.business_rules.columns()
    source_columns = [source.column for source in read_source_fields()]
    shared = [column for column in columns if column in source_columns]
    assert shared == [column for column in source_columns if column in columns]
    assert columns[: len(shared)] == shared


def test_field_settings_match_source(field_comparison: Comparison) -> None:
    """Type, requirement, limits, list/boolean input, role and defaults match Data info."""
    assert field_comparison.differences == []


def test_every_source_list_is_a_lookup_sheet_or_a_removed_field(bundle: ConfigBundle) -> None:
    """Each List Values column is a lookup sheet, unless its field was removed (CO-06)."""
    columns = bundle.business_rules.columns()
    missing = set(read_source_lists()) - set(bundle.lookup_lists.sheets)
    assert all(name not in columns for name in missing)


def test_seed_lookup_values_match_source(lookup_comparison: Comparison) -> None:
    """The seed lookup values equal List Values, after the allowed differences."""
    assert lookup_comparison.differences == []


def test_every_allowed_difference_is_used(
    field_comparison: Comparison, lookup_comparison: Comparison
) -> None:
    """Each allowed difference explains something; an unused one needs a review."""
    used = field_comparison.used_rules | lookup_comparison.used_rules
    assert used == set(ALLOWED_DIFFERENCES)
