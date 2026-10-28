"""Eval case loader tests: the synthetic case loads, the template is skipped, problems are reported.

Broken cases are made in temp copies of the synthetic case; the committed case is never changed.
"""

import json
import shutil
from pathlib import Path

import pytest
import yaml

from app.config.bundle import ConfigBundle
from app.evals.case_loader import (
    EVALS_DIR,
    CaseLoadError,
    load_case,
    load_suite,
    resolve_suite_dir,
)

CASES_DIR = EVALS_DIR / "cases"
SYNTHETIC_CASE = CASES_DIR / "synthetic_001"


@pytest.fixture
def suite_copy(tmp_path: Path) -> Path:
    """Copy the committed cases (template included) into a temp suite folder."""
    target = tmp_path / "suite"
    shutil.copytree(CASES_DIR, target)
    return target


def edit_case_yaml(folder: Path, key: str, value: object) -> None:
    """Change one key of a copied case's case.yaml."""
    path = folder / "case.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data[key] = value
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def test_synthetic_case_loads_without_warnings(bundle: ConfigBundle) -> None:
    """The committed synthetic case matches the current field rules and has fake replies."""
    case = load_case(SYNTHETIC_CASE, bundle.field_rules)
    assert case.info.source == "synthetic"
    assert case.warnings == []
    assert not case.has_field_rules_mismatch
    assert case.fake_llm_folder is not None
    assert [path.name for path in case.documents] == [
        "synthetic_001_method.docx",
        "synthetic_001_worksheet.xlsx",
    ]
    assert len(case.expected.records) == 3
    assert len(case.seeded.errors) == 1


def test_record_name_becomes_a_found_label_of_the_name_field(bundle: ConfigBundle) -> None:
    """The name under the name field's key is the record's name and that field's label."""
    case = load_case(SYNTHETIC_CASE, bundle.field_rules)
    name_key = bundle.field_rules.record_name_field().key
    record = case.expected.records[0]
    label = record.fields[name_key]
    assert label.status == "found"
    assert label.value == record.name


def test_template_folder_is_skipped(bundle: ConfigBundle) -> None:
    """`_template` is not a case."""
    loaded = load_suite(CASES_DIR, bundle.field_rules)
    assert [case.info.id for case in loaded.cases] == ["synthetic_001"]
    assert loaded.problems == []


def test_field_rules_version_mismatch_is_flagged(bundle: ConfigBundle, suite_copy: Path) -> None:
    """A case labeled against other field rules still loads, with a warning."""
    edit_case_yaml(suite_copy / "synthetic_001", "field_rules_version", "0.0-synthetic")
    case = load_case(suite_copy / "synthetic_001", bundle.field_rules)
    assert case.has_field_rules_mismatch
    assert any("0.0-synthetic" in warning for warning in case.warnings)


def test_unknown_field_key_is_a_warning(bundle: ConfigBundle, suite_copy: Path) -> None:
    """A label for a field the rules do not extract is reported and not scored."""
    path = suite_copy / "synthetic_001" / "expected_extraction.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["records"][0]["fields"]["synthetic_unknown_field"] = {"status": "not_found"}
    path.write_text(json.dumps(data), encoding="utf-8")
    case = load_case(suite_copy / "synthetic_001", bundle.field_rules)
    assert any("synthetic_unknown_field" in warning for warning in case.warnings)


def test_record_without_a_name_is_a_case_problem(bundle: ConfigBundle, suite_copy: Path) -> None:
    """An expected record with no name cannot be matched, so the case is skipped with a problem."""
    path = suite_copy / "synthetic_001" / "expected_extraction.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    name_key = bundle.field_rules.record_name_field().key
    del data["records"][0][name_key]
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = load_suite(suite_copy, bundle.field_rules)
    assert loaded.cases == []
    assert [problem.folder for problem in loaded.problems] == ["synthetic_001"]
    assert name_key in loaded.problems[0].message


def test_broken_case_yaml_is_a_case_problem(bundle: ConfigBundle, suite_copy: Path) -> None:
    """A case.yaml with a wrong source is reported with the file name."""
    edit_case_yaml(suite_copy / "synthetic_001", "source", "synthetic-unknown-source")
    with pytest.raises(CaseLoadError, match=r"case\.yaml"):
        load_case(suite_copy / "synthetic_001", bundle.field_rules)


def test_case_without_documents_is_a_case_problem(bundle: ConfigBundle, tmp_path: Path) -> None:
    """A case must have at least one document."""
    folder = tmp_path / "synthetic_empty"
    shutil.copytree(SYNTHETIC_CASE, folder, ignore=shutil.ignore_patterns("*.docx", "*.xlsx"))
    with pytest.raises(CaseLoadError, match="no documents"):
        load_case(folder, bundle.field_rules)


def test_suite_name_resolves_under_evals_and_absolute_paths_are_kept(tmp_path: Path) -> None:
    """`--suite cases` means evals/cases at the repo root; an absolute path is used as is."""
    assert resolve_suite_dir("cases") == CASES_DIR
    assert resolve_suite_dir(str(tmp_path)) == tmp_path


def test_missing_suite_folder_is_an_error(bundle: ConfigBundle, tmp_path: Path) -> None:
    """A suite folder that does not exist stops the harness with a plain message."""
    with pytest.raises(CaseLoadError, match="does not exist"):
        load_suite(tmp_path / "missing", bundle.field_rules)
