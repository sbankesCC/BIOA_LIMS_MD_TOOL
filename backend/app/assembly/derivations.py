"""Derivations (7.3): Critical, Consumable Class, Approval Type and Worksheet Template.

One small named function per derived field. Each reads the table it owns, with the grammar in
CONTRACTS §12: a column named after a loader column reads that field's value, a column named after
a context attribute reads `yes` or `no` (was it found), and the last column before Status is the
output. The target field is the one whose loader column is the output column, and a context
attribute finds its field through its `Drives` value, so no field key is written in code.
"""

from collections.abc import Callable

from pydantic import BaseModel

from app.config.business_rules import (
    ANY_OTHER_HEADING,
    ANY_VALUE,
    BLANK_WITH_ISSUE,
    EMPTY_CELL,
    NO,
    NOT_IN_PREFIX,
    STATUS_COLUMN,
    YES,
    BusinessRules,
    FieldDefinition,
    RuleTable,
    find_referenced_table,
    is_blank_cell,
    split_list_cell,
)
from app.contracts.record import StoredRecord
from app.normalization.notes import TransformNote

CRITICAL_HEADING = "Critical headings"
CLASS_HEADING = "Class table"
APPROVAL_HEADING = "Approval type table"
WORKSHEET_HEADING = "Worksheet template table"

# The note is the same whichever table could not give a value
MISSING_NOTE = TransformNote(code="DERIVED_VALUE_MISSING").to_text()


class Derived(BaseModel):
    """A derived field's new value (None for blank) and the notes explaining it."""

    key: str
    value: str | None
    notes: list[str] = []


def derive_critical(business_rules: BusinessRules, record: StoredRecord) -> Derived | None:
    """Critical: the heading the record was found under, against the Critical headings table."""
    table = find_table(business_rules, CRITICAL_HEADING)
    if table is None:
        return None
    target = find_target(business_rules, table)
    heading = find_context_text(business_rules, record, target)
    # No heading was found: the table cannot decide, so the reviewer is told
    if heading is None:
        return Derived(key=target.key, value=None, notes=[MISSING_NOTE])
    for row in table.active_rows():
        if is_heading_match(table, row, heading):
            return Derived(key=target.key, value=read_output(row, target))
    return Derived(key=target.key, value=None)


def derive_consumable_class(business_rules: BusinessRules, record: StoredRecord) -> Derived | None:
    """Consumable Class: the vendor against the Class table and the BAL vendor names."""
    return derive_from_table(business_rules, record, CLASS_HEADING)


def derive_approval_type(business_rules: BusinessRules, record: StoredRecord) -> Derived | None:
    """Approval Type: Consumable Class, Critical and the serial dilution context."""
    return derive_from_table(business_rules, record, APPROVAL_HEADING)


def derive_worksheet_template(
    business_rules: BusinessRules, record: StoredRecord
) -> Derived | None:
    """Worksheet Template: Consumable Class and Critical against the worksheet table."""
    return derive_from_table(business_rules, record, WORKSHEET_HEADING)


# In the order Assembly runs them: Approval Type and Worksheet Template read Class and Critical
DERIVATIONS: tuple[Callable[[BusinessRules, StoredRecord], Derived | None], ...] = (
    derive_critical,
    derive_consumable_class,
    derive_approval_type,
    derive_worksheet_template,
)


# ----- Finding tables and their fields -----


def find_table(business_rules: BusinessRules, heading: str) -> RuleTable | None:
    """Return the table with this heading from any field or section, or None if there is none."""
    for group in business_rules.table_groups():
        for table in group:
            if table.heading == heading:
                return table
    return None


def find_section_tables(business_rules: BusinessRules, table: RuleTable) -> list[RuleTable]:
    """Return the tables of the section that holds this table (for `in <table>` cells)."""
    return next(group for group in business_rules.table_groups() if table in group)


def find_target(business_rules: BusinessRules, table: RuleTable) -> FieldDefinition:
    """Return the field named by the table's output column (the last column before Status)."""
    output_column = [column for column in table.columns if column != STATUS_COLUMN][-1]
    return next(field for field in business_rules.fields if field.column == output_column)


def find_context_text(
    business_rules: BusinessRules, record: StoredRecord, target: FieldDefinition
) -> str | None:
    """Return the found value of the context attribute that drives the target, if any."""
    for attribute in business_rules.context_fields():
        if attribute.drives != target.key:
            continue
        found = record.context.get(attribute.key)
        extraction = found.extraction if found is not None else None
        if extraction is not None and extraction.status == "found" and extraction.value:
            return join_text(extraction.value)
    return None


def join_text(value: str | list[str]) -> str:
    """Return an extracted value as one text (a list is joined with spaces)."""
    return value if isinstance(value, str) else " ".join(value)


# ----- The Critical headings table -----


def is_heading_match(table: RuleTable, row: dict[str, str], heading: str) -> bool:
    """Return True if the heading holds a wanted phrase and none of the excluded ones."""
    contains_column, unless_column = table.columns[0], table.columns[1]
    if row[contains_column] == ANY_OTHER_HEADING:
        return True
    lowered = heading.casefold()
    wanted = [phrase.casefold() for phrase in split_list_cell(row[contains_column])]
    unwanted = [phrase.casefold() for phrase in split_list_cell(row[unless_column])]
    return any(phrase in lowered for phrase in wanted) and not any(
        phrase in lowered for phrase in unwanted
    )


# ----- Tables read with the derivation grammar -----


def derive_from_table(
    business_rules: BusinessRules, record: StoredRecord, heading: str
) -> Derived | None:
    """Return the value of the first row whose input cells all match the record."""
    table = find_table(business_rules, heading)
    if table is None:
        return None
    target = find_target(business_rules, table)
    inputs = read_inputs(business_rules, record, table, target)
    section = find_section_tables(business_rules, table)
    for row in table.active_rows():
        if all(is_cell_match(row[column], value, section) for column, value in inputs.items()):
            return read_derived(row, target)
    # No row fits (an input is itself empty): the field stays blank; the input carries the issue
    return Derived(key=target.key, value=None)


def read_inputs(
    business_rules: BusinessRules, record: StoredRecord, table: RuleTable, target: FieldDefinition
) -> dict[str, str | None]:
    """Return each input column's value: a loader field's output, or yes/no for a context key."""
    # The Status column is bookkeeping, even though a loader column has the same name
    names = business_rules.input_columns() - {target.column, STATUS_COLUMN}
    inputs: dict[str, str | None] = {}
    for column in table.columns:
        if column not in names:
            continue
        inputs[column] = read_column_value(business_rules, record, column)
    return inputs


def read_column_value(
    business_rules: BusinessRules, record: StoredRecord, column: str
) -> str | None:
    """Return a loader column's output value, or yes/no for whether a context key was found."""
    for field in business_rules.fields:
        if field.column == column:
            return record.fields[field.key].output.value or None
    found = record.context.get(column)
    extraction = found.extraction if found is not None else None
    return YES if extraction is not None and extraction.status == "found" else NO


def is_cell_match(cell: str, value: str | None, section: list[RuleTable]) -> bool:
    """Return True if an input cell accepts the value (CONTRACTS §12 grammar)."""
    if cell == ANY_VALUE:
        return True
    if cell == EMPTY_CELL:
        return value is None
    reference = find_referenced_table(cell)
    if reference is not None:
        is_listed = value is not None and is_in_table(value, reference, section)
        return not is_listed if cell.startswith(NOT_IN_PREFIX) else is_listed
    return value is not None and compare_text(value) == compare_text(cell)


def is_in_table(value: str, heading: str, section: list[RuleTable]) -> bool:
    """Return True if the value is in the first column of the named table (case, spaces ignored)."""
    for table in section:
        if table.heading == heading:
            first_column = table.columns[0]
            return any(
                compare_text(value) == compare_text(row[first_column])
                for row in table.active_rows()
            )
    return False


def compare_text(text: str) -> str:
    """Return the text without spaces and case, for comparing a value to a cell."""
    return "".join(text.split()).casefold()


def read_derived(row: dict[str, str], target: FieldDefinition) -> Derived:
    """Turn a matched row's output cell into a value; `(blank, with an issue)` adds the note."""
    cell = row[target.column]
    if cell == BLANK_WITH_ISSUE:
        return Derived(key=target.key, value=None, notes=[MISSING_NOTE])
    return Derived(key=target.key, value=read_output(row, target))


def read_output(row: dict[str, str], target: FieldDefinition) -> str | None:
    """Return a row's output cell as a value, or None for a blank cell."""
    cell = row[target.column]
    return None if is_blank_cell(cell) else cell


# ----- Startup check (called by the config bundle) -----


def find_derivation_problems(business_rules: BusinessRules) -> list[str]:
    """Return a problem for each derivation table that is missing or reads an unknown column."""
    problems: list[str] = []
    headings = (CRITICAL_HEADING, CLASS_HEADING, APPROVAL_HEADING, WORKSHEET_HEADING)
    loader_columns = business_rules.columns()
    for heading in headings:
        table = find_table(business_rules, heading)
        if table is None:
            problems.append(f"business_rules.md: the derivation table '### {heading}' is missing.")
            continue
        columns = [column for column in table.columns if column != STATUS_COLUMN]
        # The last column is the output and must be a loader column; Critical's first two
        # columns hold heading phrases, not field values
        skipped = 2 if heading == CRITICAL_HEADING else 0
        problems += [
            f"business_rules.md: '### {heading}' has the column '{column}', which is neither a "
            "loader column nor a context attribute key. Rename the column."
            for column in columns[skipped:-1]
            if column not in business_rules.input_columns()
        ]
        if columns[-1] not in loader_columns:
            problems.append(
                f"business_rules.md: the last column of '### {heading}' ('{columns[-1]}') "
                "must be the loader column of the field it derives."
            )
    return problems
