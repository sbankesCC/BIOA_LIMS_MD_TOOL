"""Happy-path tests: the real client config loads and holds what the contracts expect."""

from pathlib import Path

from app.config.bundle import ConfigBundle, load_config_bundle
from app.config.prompts import EXPECTED_PLACEHOLDERS
from app.validation.duplicates import find_name_rule
from tests.conftest import edit_business_rules


def test_business_rules_have_22_fields_13_extracted_and_2_context(bundle: ConfigBundle) -> None:
    """The business rules define 22 loader fields (13 extracted by the LLM) and 2 context ones."""
    assert len(bundle.business_rules.fields) == 22
    assert len(bundle.business_rules.extracted_fields()) == 13
    assert len(bundle.business_rules.context_fields()) == 2


def test_loader_columns_follow_the_export_template_order(bundle: ConfigBundle) -> None:
    """The bundle's loader fields are in the export template's column order."""
    assert bundle.business_rules.columns() == bundle.export_template.headers


def test_every_lookup_field_has_its_sheet(bundle: ConfigBundle) -> None:
    """Each field with a lookup sheet finds that sheet in the lookup workbook."""
    sheets = bundle.lookup_lists.sheets
    for field in bundle.business_rules.fields:
        if field.lookup_sheet is not None:
            assert field.lookup_sheet in sheets


def test_reserved_sheets_are_not_lookup_lists(bundle: ConfigBundle) -> None:
    """Sheets starting with '_' are instructions and metadata, not lookup lists."""
    assert not any(name.startswith("_") for name in bundle.lookup_lists.sheets)


def test_condition_group_codes_are_record_issues(bundle: ConfigBundle) -> None:
    """Every condition group raises a record-level issue code from the catalogue."""
    for group in bundle.business_rules.condition_groups.values():
        assert group.issue_code in bundle.issue_catalogue.record_issues


def test_all_six_prompts_load(bundle: ConfigBundle) -> None:
    """Every prompt the code uses loads with its version."""
    assert set(bundle.prompts) == set(EXPECTED_PLACEHOLDERS)
    assert len(bundle.prompts) == 6
    assert all(prompt.version for prompt in bundle.prompts.values())


def test_versions_cover_every_config_file(bundle: ConfigBundle) -> None:
    """The bundle reports a version for each config file, read from the files themselves."""
    versions = bundle.versions()
    assert versions.business_rules == bundle.business_rules.version
    assert versions.issue_catalogue == bundle.issue_catalogue.version
    assert versions.lookup_lists == bundle.lookup_lists.metadata.version_id
    assert versions.reference_data_mapping == bundle.reference_mapping.version
    assert versions.extraction_rules == bundle.extraction_rules.version
    assert versions.export_template == bundle.export_template.version
    assert set(versions.prompts) == set(bundle.prompts)


def test_record_name_field_is_found_by_its_flag_not_its_position(
    config_copy: Path, bundle: ConfigBundle
) -> None:
    """Moving the name flag to the last judge field makes that field the name, not the first."""
    last_judge_key = bundle.business_rules.duplicate_judge_fields()[-1].key
    edit_business_rules(config_copy, "| Record name | yes |\n", "")
    edit_business_rules(
        config_copy,
        f"| Key | {last_judge_key} |",
        f"| Key | {last_judge_key} |\n| Record name | yes |",
    )
    business_rules = load_config_bundle(config_copy).business_rules
    name_rule = find_name_rule(business_rules)
    assert name_rule.key == business_rules.duplicate_judge_fields()[-1].key
    assert name_rule.key != business_rules.fields[0].key


def test_record_name_field_is_sent_to_the_duplicate_judge(bundle: ConfigBundle) -> None:
    """The real config flags one name field, and it is among the duplicate judge fields."""
    judge_fields = bundle.business_rules.duplicate_judge_fields()
    assert find_name_rule(bundle.business_rules) in judge_fields
    assert all(field.role in ("extracted", "generated", "derived") for field in judge_fields)
