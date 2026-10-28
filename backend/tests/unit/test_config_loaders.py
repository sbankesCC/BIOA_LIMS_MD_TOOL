"""Happy-path tests: the real client config loads and holds what the contracts expect."""

from pathlib import Path
from typing import Any

from app.config.bundle import ConfigBundle, load_config_bundle
from app.validation.duplicates import find_name_rule
from tests.conftest import edit_yaml


def test_field_rules_have_22_fields_and_17_extracted(bundle: ConfigBundle) -> None:
    """The field rules define the 22 loader fields, 17 of them extracted by the LLM."""
    assert len(bundle.field_rules.fields) == 22
    assert len(bundle.field_rules.extracted_fields()) == 17


def test_dfd_headers_equal_field_rule_columns(bundle: ConfigBundle) -> None:
    """The template's header row is the field-rule columns, in the same order."""
    assert bundle.dfd_template.headers == bundle.field_rules.columns()


def test_every_lookup_field_has_its_sheet(bundle: ConfigBundle) -> None:
    """Each field with a lookup sheet finds that sheet in the lookup workbook."""
    sheets = bundle.lookup_lists.sheets
    for field in bundle.field_rules.fields:
        if field.lookup_sheet is not None:
            assert field.lookup_sheet in sheets


def test_reserved_sheets_are_not_lookup_lists(bundle: ConfigBundle) -> None:
    """Sheets starting with '_' are instructions and metadata, not lookup lists."""
    assert not any(name.startswith("_") for name in bundle.lookup_lists.sheets)


def test_condition_group_codes_are_record_issues(bundle: ConfigBundle) -> None:
    """Every condition group raises a record-level issue code from the catalogue."""
    for group in bundle.field_rules.condition_groups.values():
        assert group.issue_code in bundle.issue_catalogue.record_issues


def test_all_three_prompts_load(bundle: ConfigBundle) -> None:
    """The extraction, verification and duplicate judge prompts load with their versions."""
    assert set(bundle.prompts) == {"extraction", "extraction_verification", "duplicate_judge"}
    assert all(prompt.version for prompt in bundle.prompts.values())


def test_versions_cover_every_config_file(bundle: ConfigBundle) -> None:
    """The bundle reports a version for each config file, read from the files themselves."""
    versions = bundle.versions()
    assert versions.field_rules == bundle.field_rules.version
    assert versions.issue_catalogue == bundle.issue_catalogue.version
    assert versions.lookup_lists == bundle.lookup_lists.metadata.version_id
    assert versions.reference_data_mapping == bundle.reference_mapping.version
    assert versions.dfd_template.startswith("sha256:")
    assert set(versions.prompts) == set(bundle.prompts)


def test_record_name_field_is_found_by_its_flag_not_its_position(config_copy: Path) -> None:
    """Moving the name flag to the last judge field makes that field the name, not the first."""

    def change(data: Any) -> None:
        for field in data["fields"]:
            field.pop("is_record_name", None)
        judge_fields = [field for field in data["fields"] if field.get("sent_to_duplicate_judge")]
        judge_fields[-1]["is_record_name"] = True

    edit_yaml(config_copy / "field_rules.yaml", change)
    field_rules = load_config_bundle(config_copy).field_rules
    name_rule = find_name_rule(field_rules)
    assert name_rule.key == field_rules.duplicate_judge_fields()[-1].key
    assert name_rule.key != field_rules.fields[0].key


def test_record_name_field_is_sent_to_the_duplicate_judge(bundle: ConfigBundle) -> None:
    """The real config flags one name field, and it is among the duplicate judge fields."""
    judge_fields = bundle.field_rules.duplicate_judge_fields()
    assert find_name_rule(bundle.field_rules) in judge_fields
    assert all(field.role == "extracted" for field in judge_fields)
