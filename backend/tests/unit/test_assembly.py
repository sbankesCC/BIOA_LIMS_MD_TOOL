"""Assembly tests: loader values, closed conflicts, each derivation row, defaults, person values.

Field keys, lookup values and table cells are read from the client config, never written here.
"""

from pathlib import Path

import pytest

from app.assembly.assemble import USER_ORIGINS, assemble_record
from app.assembly.derivations import (
    derive_approval_type,
    derive_consumable_class,
    derive_critical,
    derive_worksheet_template,
    find_target,
)
from app.config.bundle import ConfigBundle
from app.config.business_rules import (
    ANY_OTHER_HEADING,
    IN_PREFIX,
    NOT_IN_PREFIX,
    STATUS_COLUMN,
    BusinessRules,
    FieldDefinition,
    RuleTable,
    find_referenced_table,
    is_blank_cell,
    split_list_cell,
)
from app.contracts.extraction import Alternative, ExtractedField
from app.contracts.record import FieldNormalization, FieldOutput, StoredRecord
from app.normalization.normalize import normalize_record
from app.normalization.notes import find_transform_notes
from tests.conftest import assert_config_error, edit_business_rules
from tests.unit.record_helpers import (
    EVIDENCE,
    find_business_table,
    find_field_table,
    find_lookup_rule,
    find_rule,
    found,
    make_record,
    spaced_value,
    with_output,
)

SYNTHETIC_VALUE = "Synthetic value"


def assemble_one(bundle: ConfigBundle, record: StoredRecord) -> StoredRecord:
    """Normalize then assemble a record, as the processing graph does."""
    rules = bundle.business_rules
    return assemble_record(normalize_record(record, rules, bundle.lookup_lists), rules)


def field_by_column(rules: BusinessRules, column: str) -> FieldDefinition:
    """Return the loader field with this column name."""
    return next(rule for rule in rules.fields if rule.column == column)


def output_column(table: RuleTable) -> str:
    """Return a derivation table's output column: the last one before Status."""
    return [column for column in table.columns if column != STATUS_COLUMN][-1]


def class_table(bundle: ConfigBundle) -> RuleTable:
    """Return the Class table (the Consumable Class derivation)."""
    return find_field_table(bundle, "Class table")[1]


def vendor_key(bundle: ConfigBundle) -> str:
    """Return the key of the field the Class table reads (its first column)."""
    table = class_table(bundle)
    return field_by_column(bundle.business_rules, table.columns[0]).key


def class_key(bundle: ConfigBundle) -> str:
    """Return the key of the field the Class table derives."""
    return find_target(bundle.business_rules, class_table(bundle)).key


def note_codes(output: FieldOutput) -> list[str]:
    """Return the codes of the coded notes in an output's changes, in order."""
    return [note.code for note in find_transform_notes(output.changes)]


# ----- 7.2 Loader values -----


def test_extracted_value_becomes_the_output_with_its_notes(bundle: ConfigBundle) -> None:
    """The output holds the normalized value, origin extracted, and the normalization notes."""
    rule = find_lookup_rule(bundle, is_matching_allowed=False)
    value = spaced_value(bundle, rule)
    record = make_record(bundle.business_rules, {rule.key: found(value.upper())})
    output = assemble_one(bundle, record).fields[rule.key].output
    assert output.value == value
    assert output.origin == "extracted"
    assert note_codes(output) == ["FORMAT_CORRECTED"]


def test_multi_value_field_output_is_the_joined_value(bundle: ConfigBundle) -> None:
    """Values of a multi-value field are exported joined with the field's separator."""
    rule = find_rule(bundle.business_rules, lambda rule: rule.multi_value)
    assert rule.separator is not None
    record = make_record(bundle.business_rules, {rule.key: found(["SYN-001", "SYN-002"])})
    output = assemble_one(bundle, record).fields[rule.key].output
    assert output.value == rule.separator.join(["SYN-001", "SYN-002"])


def test_value_waiting_for_matching_is_not_exported(bundle: ConfigBundle) -> None:
    """A value left for Matching has no output; the suggestion is never applied by code."""
    rule = find_lookup_rule(bundle, is_matching_allowed=True)
    record = make_record(bundle.business_rules, {rule.key: found(SYNTHETIC_VALUE)})
    output = assemble_one(bundle, record).fields[rule.key].output
    assert output.value is None
    assert output.origin == "extracted"


# ----- 7.1 Conflicts -----


def conflict_of(first: str, second: str) -> ExtractedField:
    """Return a conflicting field with two alternatives."""
    return ExtractedField(
        status="conflicting",
        alternatives=[
            Alternative(value=first, evidence=[EVIDENCE]),
            Alternative(value=second, evidence=[EVIDENCE]),
        ],
        warning="synthetic conflict",
    )


@pytest.mark.rule("GEN-08")
def test_alternatives_identical_after_normalization_close_the_conflict(
    bundle: ConfigBundle,
) -> None:
    """Two spellings of one list value become that value, with a CONFLICT_CLOSED note."""
    rule = find_lookup_rule(bundle, is_matching_allowed=False)
    value = spaced_value(bundle, rule)
    record = make_record(bundle.business_rules, {rule.key: conflict_of(value.upper(), value)})
    output = assemble_one(bundle, record).fields[rule.key].output
    assert output.value == value
    assert "CONFLICT_CLOSED" in note_codes(output)


@pytest.mark.rule("GEN-09")
def test_alternatives_that_still_differ_stay_a_conflict(bundle: ConfigBundle) -> None:
    """Different values after normalization leave the output empty for the reviewer."""
    rule = find_lookup_rule(bundle, is_matching_allowed=False)
    record = make_record(
        bundle.business_rules, {rule.key: conflict_of("Synthetic one", "Synthetic two")}
    )
    output = assemble_one(bundle, record).fields[rule.key].output
    assert output.value is None
    assert output.changes == [] or "CONFLICT_CLOSED" not in note_codes(output)


# ----- 7.3 Derivations -----


def critical_rows(bundle: ConfigBundle) -> tuple[FieldDefinition, RuleTable]:
    """Return the Critical field and its headings table."""
    return find_field_table(bundle, "Critical headings")


def heading_record(bundle: ConfigBundle, heading: str | None) -> StoredRecord:
    """Return a record whose context holds this source heading (not found when None)."""
    attribute = next(a for a in bundle.business_rules.context_fields() if a.drives == "critical")
    context = {attribute.key: found(heading)} if heading else {}
    return make_record(bundle.business_rules, context=context)


@pytest.mark.rule("CR-01")
@pytest.mark.rule("CR-02")
def test_critical_follows_the_headings_table_row_by_row(bundle: ConfigBundle) -> None:
    """A wanted phrase gives the first row's value; otherwise the last row's."""
    rule, table = critical_rows(bundle)
    first, last = table.active_rows()[0], table.active_rows()[-1]
    column = output_column(table)
    assert last["Heading contains"] == ANY_OTHER_HEADING
    phrase = split_list_cell(first["Heading contains"])[0]
    unwanted = split_list_cell(first["Unless it contains"])[0]
    cases = {
        f"Table 3. {phrase}s": first[column],
        f"Table 4. {unwanted} {phrase}s": last[column],
        "Table 5. Synthetic heading": last[column],
    }
    for heading, expected in cases.items():
        derived = derive_critical(bundle.business_rules, heading_record(bundle, heading))
        assert derived is not None
        assert (derived.key, derived.value) == (rule.key, expected), heading


@pytest.mark.rule("CR-01")
def test_critical_with_no_heading_is_blank_with_a_note(bundle: ConfigBundle) -> None:
    """No source heading was found: Critical stays blank and DERIVED_VALUE_MISSING is noted."""
    derived = derive_critical(bundle.business_rules, heading_record(bundle, None))
    assert derived is not None
    assert derived.value is None
    assert [n.code for n in find_transform_notes(derived.notes)] == ["DERIVED_VALUE_MISSING"]


def vendor_record(bundle: ConfigBundle, vendor: str | None) -> StoredRecord:
    """Return a record whose vendor output (what the Class table reads) is this vendor."""
    rules = bundle.business_rules
    output = FieldOutput(value=vendor, origin="extracted")
    return with_output(make_record(rules), vendor_key(bundle), output)


@pytest.mark.rule("CC-02")
@pytest.mark.rule("CC-03")
@pytest.mark.rule("CC-06")
def test_consumable_class_follows_the_class_table_row_by_row(bundle: ConfigBundle) -> None:
    """A BAL vendor (any case) gives the `in` row, another vendor `not in`, none the issue."""
    rules = bundle.business_rules
    table = class_table(bundle)
    first_column, column = table.columns[0], output_column(table)
    rows = table.active_rows()
    in_row = next(r[column] for r in rows if r[first_column].startswith(IN_PREFIX))
    not_in_row = next(r[column] for r in rows if r[first_column].startswith(NOT_IN_PREFIX))
    names = find_business_names(bundle, table)
    for name in names:
        derived = derive_consumable_class(rules, vendor_record(bundle, f" {name.upper()} "))
        assert derived is not None
        assert derived.value == in_row
    other = derive_consumable_class(rules, vendor_record(bundle, "Synthetic Vendor Inc"))
    assert other is not None
    assert other.value == not_in_row
    empty = derive_consumable_class(rules, vendor_record(bundle, None))
    assert empty is not None
    assert empty.value is None
    assert [n.code for n in find_transform_notes(empty.notes)] == ["DERIVED_VALUE_MISSING"]


def find_business_names(bundle: ConfigBundle, class_table: RuleTable) -> list[str]:
    """Return the vendor names of the table an `in <table>` cell of the class table names."""
    cell = next(
        row[class_table.columns[0]]
        for row in class_table.active_rows()
        if find_referenced_table(row[class_table.columns[0]])
    )
    heading = find_referenced_table(cell)
    owner, _ = find_field_table(bundle, class_table.heading)
    table = next(t for t in owner.tables if t.heading == heading)
    return [row[table.columns[0]] for row in table.active_rows()]


def fill_inputs(
    rules: BusinessRules, record: StoredRecord, table: RuleTable, row: dict[str, str]
) -> StoredRecord:
    """Return a record whose input columns hold what one table row asks for."""
    for column in table.columns[:-2]:
        cell = row[column]
        field = next((f for f in rules.fields if f.column == column), None)
        if field is not None:
            value = None if is_blank_cell(cell) else (SYNTHETIC_VALUE if cell == "any" else cell)
            record = with_output(record, field.key, FieldOutput(value=value, origin="derived"))
            continue
        attribute = next(a for a in rules.context_fields() if a.key == column)
        status = "found" if cell == "yes" else "not_found"
        extraction = ExtractedField(status=status, value="x" if cell == "yes" else None)
        context = {
            **record.context,
            attribute.key: record.context[attribute.key].model_copy(
                update={"extraction": extraction}
            ),
        }
        record = record.model_copy(update={"context": context})
    return record


@pytest.mark.rule("AT-01")
def test_approval_type_follows_every_row_of_its_table(bundle: ConfigBundle) -> None:
    """Each row's inputs give that row's Approval Type (blank cells stay blank)."""
    rules = bundle.business_rules
    table = find_business_table(rules, "Approval type table")
    for row in table.active_rows():
        record = fill_inputs(rules, make_record(rules), table, row)
        derived = derive_approval_type(rules, record)
        assert derived is not None
        expected = row[output_column(table)]
        assert derived.value == (None if is_blank_cell(expected) else expected)


@pytest.mark.rule("WT-01")
@pytest.mark.rule("WT-02")
@pytest.mark.rule("WT-03")
def test_worksheet_template_follows_every_row_of_its_table(bundle: ConfigBundle) -> None:
    """Each row's inputs give that row's Worksheet Template (blank cells stay blank)."""
    rules = bundle.business_rules
    _, table = find_field_table(bundle, "Worksheet template table")
    for row in table.active_rows():
        record = fill_inputs(rules, make_record(rules), table, row)
        derived = derive_worksheet_template(rules, record)
        assert derived is not None
        expected = row[output_column(table)]
        assert derived.value == (None if is_blank_cell(expected) else expected)


def test_derived_fields_are_written_in_order_with_origin_derived(bundle: ConfigBundle) -> None:
    """Assembly derives Critical, then Class, then the two fields that read them."""
    rules = bundle.business_rules
    _, headings = critical_rows(bundle)
    first = headings.active_rows()[0]
    heading = f"Table 1. {split_list_cell(first['Heading contains'])[0]}s"
    attribute = next(a for a in rules.context_fields() if a.drives == "critical")
    record = make_record(rules, context={attribute.key: found(heading)})
    result = assemble_one(bundle, record)
    for rule in rules.derived_fields():
        assert result.fields[rule.key].output.origin == "derived"
    critical = result.fields[find_target(rules, headings).key]
    assert critical.output.value == first[output_column(headings)]


@pytest.mark.rule("AT-01")
def test_derived_fields_recomputed_on_recheck(bundle: ConfigBundle) -> None:
    """A person's change to the vendor changes Consumable Class the next time Assembly runs."""
    rules = bundle.business_rules
    table = class_table(bundle)
    first = assemble_one(bundle, make_record(rules))
    assert first.fields[class_key(bundle)].output.value is None
    name = find_business_names(bundle, table)[0]
    edited = with_output(first, vendor_key(bundle), FieldOutput(value=name, origin="user_edited"))
    second = assemble_record(edited, rules)
    expected = next(
        r[output_column(table)]
        for r in table.active_rows()
        if r[table.columns[0]].startswith(IN_PREFIX)
    )
    assert second.fields[class_key(bundle)].output.value == expected
    assert second.fields[class_key(bundle)].output.origin == "derived"


# ----- 7.4 and 7.5 Defaults, roles, person values -----


@pytest.mark.rule("TM-03")
def test_default_is_applied_to_not_found_field(bundle: ConfigBundle) -> None:
    """A not-found field with a default gets it, with origin default and DEFAULT_APPLIED."""
    rule = find_rule(bundle.business_rules, lambda rule: rule.default is not None)
    output = assemble_one(bundle, make_record(bundle.business_rules)).fields[rule.key].output
    assert output.value == rule.default
    assert output.origin == "default"
    [note] = find_transform_notes(output.changes)
    assert (note.code, note.value) == ("DEFAULT_APPLIED", rule.default)


def test_default_does_not_replace_found_value(bundle: ConfigBundle) -> None:
    """A field with a default keeps the value found in the documents."""
    rule = find_rule(bundle.business_rules, lambda rule: rule.default is not None)
    other = next(v for v in find_values(bundle, rule) if v != rule.default)
    record = make_record(bundle.business_rules, {rule.key: found(other)})
    output = assemble_one(bundle, record).fields[rule.key].output
    assert (output.value, output.origin) == (other, "extracted")


def find_values(bundle: ConfigBundle, rule: FieldDefinition) -> list[str]:
    """Return the values a field may hold: its lookup list, or Y and N for a boolean."""
    if rule.lookup_sheet is not None:
        return bundle.lookup_lists.sheets[rule.lookup_sheet]
    return ["Y", "N"]


def test_default_is_not_applied_to_conflicting_field(bundle: ConfigBundle) -> None:
    """A conflicting field stays empty for the user's choice, even when it has a default."""
    rule = find_rule(bundle.business_rules, lambda rule: rule.default is not None)
    record = make_record(
        bundle.business_rules, {rule.key: conflict_of("Synthetic one", "Synthetic two")}
    )
    output = assemble_one(bundle, record).fields[rule.key].output
    assert output.value is None
    assert output.origin == "extracted"


def test_default_is_not_applied_to_a_value_waiting_for_a_choice(bundle: ConfigBundle) -> None:
    """A matching value or reviewer choices mean the field is unresolved, not empty."""
    rule = find_rule(bundle.business_rules, lambda rule: rule.default is not None)
    record = make_record(bundle.business_rules, {rule.key: found(SYNTHETIC_VALUE)})
    stored = record.fields[rule.key].model_copy(
        update={"normalization": FieldNormalization(choices=["Synthetic choice"])}
    )
    waiting = record.model_copy(update={"fields": {**record.fields, rule.key: stored}})
    output = assemble_record(waiting, bundle.business_rules).fields[rule.key].output
    assert output.value is None


def test_not_found_field_without_default_stays_empty(bundle: ConfigBundle) -> None:
    """Nothing is invented: a not-found field with no default has no value."""
    rule = find_rule(bundle.business_rules, lambda rule: rule.default is None)
    output = assemble_one(bundle, make_record(bundle.business_rules)).fields[rule.key].output
    assert output.value is None
    assert output.changes == []


def test_blank_for_now_and_system_fields_are_empty(bundle: ConfigBundle) -> None:
    """Fields the tool does not fill are empty, with their role as origin."""
    result = assemble_one(bundle, make_record(bundle.business_rules))
    for rule in bundle.business_rules.fields:
        if rule.role in ("blank_for_now", "system"):
            assert result.fields[rule.key].output == FieldOutput(value=None, origin=rule.role)


def test_assembly_never_overwrites_person_value(bundle: ConfigBundle) -> None:
    """A value a person set (typed, fixed, used suggestion) is kept exactly, on any field role."""
    rules = bundle.business_rules
    keys = [
        find_rule(rules, lambda rule: rule.default is not None).key,
        rules.derived_fields()[0].key,
        class_key(bundle),
    ]
    for key in keys:
        for origin in USER_ORIGINS:
            user_output = FieldOutput(
                value="Synthetic user value", origin=origin, changes=["by user"]
            )
            record = with_output(make_record(rules), key, user_output)
            assert assemble_one(bundle, record).fields[key].output == user_output


def test_assembly_writes_only_the_output_section(bundle: ConfigBundle) -> None:
    """Extraction, normalization, verification, suggestion and issue IDs are left as they were."""
    rule = find_lookup_rule(bundle, is_matching_allowed=True)
    record = normalize_record(
        make_record(bundle.business_rules, {rule.key: found(SYNTHETIC_VALUE)}),
        bundle.business_rules,
        bundle.lookup_lists,
    )
    result = assemble_record(record, bundle.business_rules)
    for key, field in result.fields.items():
        assert field.model_copy(update={"output": record.fields[key].output}) == record.fields[key]
    assert result.context == record.context


def test_assembly_is_repeatable(bundle: ConfigBundle) -> None:
    """Assembling an already assembled record gives the same record."""
    rule = find_lookup_rule(bundle, is_matching_allowed=False)
    record = make_record(bundle.business_rules, {rule.key: found(spaced_value(bundle, rule))})
    once = assemble_one(bundle, record)
    assert assemble_record(once, bundle.business_rules) == once


# ----- Startup check -----


def test_derivation_table_with_an_unknown_column_is_reported(config_copy: Path) -> None:
    """A derivation table column that is no loader column or context key stops loading."""
    edit_business_rules(
        config_copy,
        "| Consumable Class | Critical | Worksheet Template |",
        "| Synthetic Column | Critical | Worksheet Template |",
    )
    assert_config_error(config_copy, "has the column 'Synthetic Column'")
