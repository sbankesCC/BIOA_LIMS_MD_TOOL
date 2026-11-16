"""Normalization tests: each substep (4.1 to 4.7) on synthetic records.

Field keys, lookup values and table cells are read from the client config, never written here.
"""

import pytest

from app.config.bundle import ConfigBundle
from app.config.business_rules import FieldDefinition, is_blank_cell, split_list_cell
from app.contracts.extraction import Alternative, ExtractedField
from app.contracts.record import FieldNormalization, StoredRecord
from app.normalization.characters import build_character_map
from app.normalization.lookup_values import find_allowed_values
from app.normalization.normalize import normalize_record
from app.normalization.notes import COLLAPSED_SPACES, TRIMMED_WHITESPACE, find_transform_notes
from tests.unit.record_helpers import (
    EVIDENCE,
    TRANSLATION_HEADING,
    find_field_table,
    find_lookup_rule,
    find_rule,
    found,
    make_record,
    spaced_value,
)

UNITS_HEADING = "Concentration units"


def normalize_one(bundle: ConfigBundle, key: str, extraction: ExtractedField) -> FieldNormalization:
    """Normalize a record with one extracted field and return that field's normalization."""
    record = make_record(bundle.business_rules, {key: extraction})
    result = normalize_record(record, bundle.business_rules, bundle.lookup_lists)
    normalization = result.fields[key].normalization
    assert normalization is not None
    return normalization


def note_codes(normalization: FieldNormalization) -> list[str]:
    """Return the codes of the coded notes of a normalization, in order."""
    return [note.code for note in find_transform_notes(normalization.notes)]


# ----- 4.1 Clean text -----


@pytest.mark.rule("GEN-04")
def test_found_text_value_is_cleaned(bundle: ConfigBundle) -> None:
    """A plain text field is trimmed and its spaces collapsed, with clean-up notes."""
    rule = find_rule(
        bundle.business_rules, lambda rule: rule.type == "text" and not rule.lookup_sheet
    )
    normalization = normalize_one(bundle, rule.key, found("  synthetic   name "))
    assert normalization.value == "synthetic name"
    assert normalization.notes == [TRIMMED_WHITESPACE, COLLAPSED_SPACES]


def test_multi_value_field_is_joined_with_separator(bundle: ConfigBundle) -> None:
    """A multi-value field's values are cleaned and joined with the configured separator."""
    rule = find_rule(bundle.business_rules, lambda rule: rule.multi_value)
    assert rule.separator is not None
    normalization = normalize_one(bundle, rule.key, found(["SYN-001 ", "SYN-002"]))
    assert normalization.value == rule.separator.join(["SYN-001", "SYN-002"])


# ----- 4.2 Characters -----


@pytest.mark.rule("GEN-03")
def test_every_character_in_the_table_is_replaced(bundle: ConfigBundle) -> None:
    """Each micro or Greek character of the table is replaced in a text field."""
    character_map = build_character_map(bundle.business_rules)
    assert character_map
    rule = find_rule(
        bundle.business_rules, lambda rule: rule.type == "text" and not rule.lookup_sheet
    )
    for character, replacement in character_map.items():
        normalization = normalize_one(bundle, rule.key, found(f"synthetic 5 {character}g"))
        assert normalization.value == f"synthetic 5 {replacement}g"
        assert any(character in note for note in normalization.notes)


# ----- 4.3 Translation tables -----


def find_rows(bundle: ConfigBundle, match_type: str) -> list[tuple[str, dict[str, str]]]:
    """Return (field key, row) for every active translation row of this match type."""
    rows: list[tuple[str, dict[str, str]]] = []
    for rule in bundle.business_rules.fields:
        for table in rule.tables:
            if table.heading == TRANSLATION_HEADING:
                rows += [
                    (rule.key, r) for r in table.active_rows() if r["Match type"] == match_type
                ]
    return rows


@pytest.mark.rule("SC-T01")
def test_every_phrase_row_translates_each_of_its_wordings(bundle: ConfigBundle) -> None:
    """A phrase gives its row's lookup value, in any case, with a note naming the row."""
    rows = [
        (key, row)
        for key, row in find_rows(bundle, "phrase")
        if not is_blank_cell(row["Lookup value"])
    ]
    assert rows
    for key, row in rows:
        for wording in split_list_cell(row["Document wording"]):
            normalization = normalize_one(bundle, key, found(wording.upper()))
            assert normalization.value == row["Lookup value"], (row["Entry"], wording)
            assert any(row["Entry"] in note for note in normalization.notes)


@pytest.mark.rule("SC-T07")
def test_range_row_matches_a_temperature_from_min_to_max_inclusive(bundle: ConfigBundle) -> None:
    """A single stated temperature inside the range (ends included) gives the row's value."""
    [(key, row)] = find_rows(bundle, "range")[:1]
    low, high = float(row["Min °C"]), float(row["Max °C"])
    for temperature in (low, high):
        normalization = normalize_one(bundle, key, found(f"{temperature:g} °C"))
        assert normalization.value == row["Lookup value"]
    outside = normalize_one(bundle, key, found(f"{high + 1:g} °C"))
    assert outside.value != row["Lookup value"]


@pytest.mark.rule("SC-T09")
@pytest.mark.rule("SC-03")
def test_reviewer_chooses_row_leaves_the_value_blank_with_choices(bundle: ConfigBundle) -> None:
    """A "Reviewer chooses" row gives no value, its choices and a note; never Matching."""
    rows = [
        (key, row) for key, row in find_rows(bundle, "phrase") if is_blank_cell(row["Lookup value"])
    ]
    assert rows
    for key, row in rows:
        wording = split_list_cell(row["Document wording"])[0]
        normalization = normalize_one(bundle, key, found(wording))
        assert normalization.value is None
        assert normalization.choices == split_list_cell(row["Reviewer chooses"])
        assert normalization.matching_value is None
        assert "REVIEWER_CHOICE_NEEDED" in note_codes(normalization)


@pytest.mark.rule("TM-T01")
def test_translation_table_of_another_field_is_used(bundle: ConfigBundle) -> None:
    """A field with a translation table and no Matching gets its code from the table."""
    phrase_rows = [
        (key, row)
        for key, row in find_rows(bundle, "phrase")
        if not is_blank_cell(row["Lookup value"]) and not find_field(bundle, key).matching_allowed
    ]
    assert phrase_rows
    key, row = phrase_rows[0]
    wording = split_list_cell(row["Document wording"])[0]
    assert normalize_one(bundle, key, found(wording)).value == row["Lookup value"]


def find_field(bundle: ConfigBundle, key: str) -> FieldDefinition:
    """Return a field definition by key."""
    return next(rule for rule in bundle.business_rules.fields if rule.key == key)


# ----- 4.4 Lookup matching -----


@pytest.mark.rule("GEN-06")
def test_exact_lookup_value_is_kept(bundle: ConfigBundle) -> None:
    """A lookup value written exactly as on the list is kept with no notes."""
    rule = find_lookup_rule(bundle, is_matching_allowed=False)
    value = spaced_value(bundle, rule)
    normalization = normalize_one(bundle, rule.key, found(value))
    assert normalization.value == value
    assert normalization.notes == []


@pytest.mark.rule("GEN-06")
def test_lookup_value_in_other_case_is_format_corrected(bundle: ConfigBundle) -> None:
    """A lookup value in upper case is matched to the list's spelling with FORMAT_CORRECTED."""
    rule = find_lookup_rule(bundle, is_matching_allowed=False)
    value = spaced_value(bundle, rule)
    normalization = normalize_one(bundle, rule.key, found(value.upper()))
    assert normalization.value == value
    [note] = find_transform_notes(normalization.notes)
    assert (note.code, note.original, note.value) == ("FORMAT_CORRECTED", value.upper(), value)


@pytest.mark.rule("GEN-06")
def test_lookup_value_with_degree_sign_and_spaces_is_matched(bundle: ConfigBundle) -> None:
    """A list value written with extra spaces and a degree sign still matches."""
    rule = find_lookup_rule(bundle, is_matching_allowed=False)
    value = spaced_value(bundle, rule)
    written = value.replace(" ", " ° ", 1).lower()
    normalization = normalize_one(bundle, rule.key, found(written))
    assert normalization.value == value
    assert note_codes(normalization) == ["FORMAT_CORRECTED"]


@pytest.mark.rule("GEN-06")
def test_unknown_value_of_a_field_without_matching_is_kept_with_not_in_lookup(
    bundle: ConfigBundle,
) -> None:
    """A value with no list match stays as written (no Matching) and is noted NOT_IN_LOOKUP."""
    rule = find_lookup_rule(bundle, is_matching_allowed=False)
    normalization = normalize_one(bundle, rule.key, found("Synthetic unlisted value"))
    assert normalization.value == "Synthetic unlisted value"
    assert normalization.matching_value is None
    assert note_codes(normalization) == ["NOT_IN_LOOKUP"]


@pytest.mark.rule("SC-04")
def test_unknown_value_of_a_matching_field_goes_to_matching(bundle: ConfigBundle) -> None:
    """A field that allows Matching keeps no value; its text is the matching value."""
    rule = find_lookup_rule(bundle, is_matching_allowed=True)
    normalization = normalize_one(bundle, rule.key, found("Synthetic unlisted value"))
    assert normalization.value is None
    assert normalization.matching_value == "Synthetic unlisted value"
    assert note_codes(normalization) == ["NOT_IN_LOOKUP"]


def test_boolean_field_lower_case_becomes_upper_case(bundle: ConfigBundle) -> None:
    """A boolean field written as "n" is normalized to N."""
    rule = find_rule(bundle.business_rules, lambda rule: rule.type == "boolean")
    normalization = normalize_one(bundle, rule.key, found("n"))
    assert normalization.value == "N"
    assert note_codes(normalization) == ["FORMAT_CORRECTED"]


@pytest.mark.rule("GEN-07")
def test_excluded_values_are_not_allowed_for_their_step(bundle: ConfigBundle) -> None:
    """An excluded value is removed from the allowed values of the steps its row names."""
    table = next(
        t for t in bundle.business_rules.general.tables if t.heading == "Excluded lookup values"
    )
    for row in table.active_rows():
        if row["Match"] != "exact" or row["Lookup list"] == "(all lists)":
            continue
        rule = next(
            (r for r in bundle.business_rules.fields if r.lookup_sheet == row["Lookup list"]), None
        )
        if rule is None:
            continue
        for step in ("Normalization", "Matching"):
            allowed = find_allowed_values(rule, bundle.business_rules, bundle.lookup_lists, step)
            is_excluded = row["Excluded from"] in ("all steps", step)
            assert (row["Value"] in allowed) is not is_excluded, (row["Value"], step)


@pytest.mark.rule("GEN-07")
def test_value_with_an_excluded_prefix_is_never_chosen(bundle: ConfigBundle) -> None:
    """A list value starting with an excluded prefix is not chosen, even when written exactly."""
    table = next(
        t for t in bundle.business_rules.general.tables if t.heading == "Excluded lookup values"
    )
    prefix = next(row["Value"] for row in table.active_rows() if row["Match"] == "prefix")
    rule = find_lookup_rule(bundle, is_matching_allowed=False)
    assert rule.lookup_sheet is not None
    planted = f"{prefix}Synthetic"
    sheets = {**bundle.lookup_lists.sheets, rule.lookup_sheet: [planted]}
    lists = bundle.lookup_lists.model_copy(update={"sheets": sheets})
    record = make_record(bundle.business_rules, {rule.key: found(planted)})
    result = normalize_record(record, bundle.business_rules, lists)
    normalization = result.fields[rule.key].normalization
    assert normalization is not None
    assert note_codes(normalization) == ["NOT_IN_LOOKUP"]


# ----- 4.5 Numbers -----


def test_number_field_reads_number_from_text(bundle: ConfigBundle) -> None:
    """A decimal field written with a unit gives the number, noted as NUMBER_READ_FROM_TEXT."""
    rule = find_rule(
        bundle.business_rules,
        lambda rule: (
            rule.type == "decimal" and not any(t.heading == UNITS_HEADING for t in rule.tables)
        ),
    )
    normalization = normalize_one(bundle, rule.key, found("1e4 cps/uL"))
    assert normalization.value == "10000"
    [note] = find_transform_notes(normalization.notes)
    assert (note.code, note.original) == ("NUMBER_READ_FROM_TEXT", "1e4 cps/uL")


def test_unreadable_number_is_kept_as_written(bundle: ConfigBundle) -> None:
    """A number field with no single number keeps the text, for validation to flag."""
    rule = find_rule(bundle.business_rules, lambda rule: rule.type == "integer")
    normalization = normalize_one(bundle, rule.key, found("several"))
    assert normalization.value == "several"
    assert normalization.notes == []


# ----- 4.6 Concentration -----


def concentration_key_and_units(bundle: ConfigBundle) -> tuple[str, list[str]]:
    """Return the concentration field's key and the example units of its units table."""
    rule, table = find_field_table(bundle, UNITS_HEADING)
    examples = [unit for row in table.active_rows() for unit in split_list_cell(row["Examples"])]
    return rule.key, examples


@pytest.mark.rule("TC-02")
def test_number_before_a_concentration_unit_gives_the_number(bundle: ConfigBundle) -> None:
    """Every example unit of the units table is accepted after a number."""
    key, examples = concentration_key_and_units(bundle)
    for unit in examples:
        normalization = normalize_one(bundle, key, found(f"5 {unit}"))
        assert normalization.value == "5", unit
        assert normalization.notes == []


@pytest.mark.rule("TC-02")
def test_a_unit_matching_a_contains_pattern_is_accepted(bundle: ConfigBundle) -> None:
    """A unit not listed in Examples is accepted when the pattern says it contains "/"."""
    key, _ = concentration_key_and_units(bundle)
    normalization = normalize_one(bundle, key, found("7 pg/mL"))
    assert normalization.value == "7"


@pytest.mark.rule("TC-03")
def test_scientific_notation_is_read_and_noted(bundle: ConfigBundle) -> None:
    """A number in scientific notation before a unit is written in full, with a note."""
    key, examples = concentration_key_and_units(bundle)
    normalization = normalize_one(bundle, key, found(f"1.6e4 {examples[0]}"))
    assert normalization.value == format(1.6e4, ".0f")
    assert note_codes(normalization) == ["NUMBER_READ_FROM_TEXT"]


@pytest.mark.rule("TC-03")
@pytest.mark.rule("TC-04")
@pytest.mark.parametrize("text", ["1:100", "10x", "0.5", "half-strength", "10x PBS + Tween"])
def test_anything_that_is_not_a_concentration_is_blank_with_a_note(
    bundle: ConfigBundle, text: str
) -> None:
    """A ratio, a multiplier, a number without a unit and other text are left blank."""
    key, _ = concentration_key_and_units(bundle)
    normalization = normalize_one(bundle, key, found(text))
    assert normalization.value is None
    assert note_codes(normalization) == ["NOT_A_CONCENTRATION"]


# ----- 4.7 Conflicts and sections -----


def test_each_alternative_of_a_conflict_is_normalized(bundle: ConfigBundle) -> None:
    """A conflicting field gets one normalized text per alternative and no single value."""
    rule = find_lookup_rule(bundle, is_matching_allowed=False)
    value = spaced_value(bundle, rule)
    conflict = ExtractedField(
        status="conflicting",
        alternatives=[
            Alternative(value=value.upper(), evidence=[EVIDENCE]),
            Alternative(value=f" {value} ", evidence=[EVIDENCE]),
        ],
        warning="synthetic conflict",
    )
    normalization = normalize_one(bundle, rule.key, conflict)
    assert normalization.value is None
    assert normalization.alternatives == [value, value]


def test_not_found_field_has_no_normalization(bundle: ConfigBundle) -> None:
    """Nothing is invented: a field with no value has no normalization section."""
    rule = find_rule(bundle.business_rules, lambda rule: rule.default is None)
    record = make_record(bundle.business_rules)
    result = normalize_record(record, bundle.business_rules, bundle.lookup_lists)
    assert result.fields[rule.key].normalization is None


def test_normalization_writes_only_the_normalization_section(bundle: ConfigBundle) -> None:
    """Every other section of every field is left exactly as it was."""
    rule = find_lookup_rule(bundle, is_matching_allowed=True)
    record = make_record(bundle.business_rules, {rule.key: found("synthetic value")})
    result = normalize_record(record, bundle.business_rules, bundle.lookup_lists)
    for key, field in result.fields.items():
        before = record.fields[key]
        assert field.model_copy(update={"normalization": None}) == before
    assert result.context == record.context


def test_normalization_is_repeatable(bundle: ConfigBundle) -> None:
    """Normalizing an already normalized record gives the same record."""
    rule = find_lookup_rule(bundle, is_matching_allowed=True)
    record: StoredRecord = make_record(
        bundle.business_rules, {rule.key: found(" synthetic value ")}
    )
    once = normalize_record(record, bundle.business_rules, bundle.lookup_lists)
    assert normalize_record(once, bundle.business_rules, bundle.lookup_lists) == once
