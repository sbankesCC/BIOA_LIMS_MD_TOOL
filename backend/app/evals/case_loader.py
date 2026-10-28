"""Eval case loader: reads a suite's case folders (CONTRACTS §9) and checks them against the config.

A case whose files are broken is skipped and reported as a problem. A case labeled against other
field rules, or naming fields the current rules do not extract, still runs with a warning.
"""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.config.errors import ConfigError, parse_model, read_yaml
from app.config.field_rules import FieldRules
from app.contracts.base import ContractModel
from app.contracts.eval_case import (
    EvalCaseInfo,
    ExpectedExtraction,
    ExpectedField,
    ExpectedRecord,
    SeededErrors,
)
from app.settings import PROJECT_ROOT
from app.transform.lookup_matching import normalize_for_match

# Suites are folders under `evals/` at the repo root (e.g. `cases`), whatever the working folder
EVALS_DIR = PROJECT_ROOT / "evals"
REPORTS_DIR = EVALS_DIR / "reports"
SCORING_FILE = "scoring.yaml"

# Files and folders of one case
CASE_FILE = "case.yaml"
EXPECTED_FILE = "expected_extraction.json"
SEEDED_FILE = "seeded_errors.json"
DOCUMENTS_FOLDER = "documents"
FAKE_LLM_FOLDER = "fake_llm"

# Folders starting with these are not cases (`_template`, hidden folders); nor are these files
SKIPPED_PREFIXES = ("_", ".")


class CaseLoadError(Exception):
    """Raised when a case folder cannot be read; the message says which file and what to fix."""


class UnscoredField(BaseModel):
    """A field left out of automatic scoring, with the reason."""

    key: str
    reason: str


class ScoringConfig(BaseModel):
    """Eval scoring settings from `evals/scoring.yaml`."""

    unscored_fields: list[UnscoredField] = []

    def unscored_keys(self) -> set[str]:
        """Return the keys of the unscored fields."""
        return {field.key for field in self.unscored_fields}


class RawExpectedExtraction(ContractModel):
    """`expected_extraction.json` before each record's name is read from its name field key."""

    records: list[dict[str, Any]]
    excluded_items: list[str] = []


class EvalCase(BaseModel):
    """One loaded case: its info, labels, documents, fake replies (if any) and warnings."""

    folder: Path
    info: EvalCaseInfo
    expected: ExpectedExtraction
    seeded: SeededErrors
    documents: list[Path]
    fake_llm_folder: Path | None = None
    has_field_rules_mismatch: bool = False
    warnings: list[str] = []


class CaseProblem(BaseModel):
    """A case folder that could not be loaded, and why."""

    folder: str
    message: str


class SuiteCases(BaseModel):
    """The loaded cases of a suite, plus the folders that could not be loaded."""

    cases: list[EvalCase]
    problems: list[CaseProblem]


def resolve_suite_dir(suite: str) -> Path:
    """Return a suite's folder: an absolute path as given, else a folder under `evals/`."""
    path = Path(suite)
    if path.is_absolute():
        return path
    return EVALS_DIR / path


def load_scoring_config(evals_dir: Path = EVALS_DIR) -> ScoringConfig:
    """Read `scoring.yaml` from the evals folder; without the file every field is scored."""
    path = evals_dir / SCORING_FILE
    if not path.is_file():
        return ScoringConfig()
    return parse_model(ScoringConfig, read_yaml(path), SCORING_FILE)


def load_suite(suite_dir: Path, field_rules: FieldRules) -> SuiteCases:
    """Load every case folder of a suite; broken ones become problems, not errors."""
    if not suite_dir.is_dir():
        raise CaseLoadError(f"The eval suite folder {suite_dir} does not exist. Check --suite.")
    cases: list[EvalCase] = []
    problems: list[CaseProblem] = []
    for folder in find_case_folders(suite_dir):
        try:
            cases.append(load_case(folder, field_rules))
        except CaseLoadError as error:
            problems.append(CaseProblem(folder=folder.name, message=str(error)))
    return SuiteCases(cases=cases, problems=problems)


def find_case_folders(suite_dir: Path) -> list[Path]:
    """Return the case folders of a suite in name order, skipping the template and hidden ones."""
    return sorted(
        path
        for path in suite_dir.iterdir()
        if path.is_dir() and not path.name.startswith(SKIPPED_PREFIXES)
    )


def load_case(folder: Path, field_rules: FieldRules) -> EvalCase:
    """Load one case folder; raise CaseLoadError if a file is missing or broken."""
    info = read_case_model(EvalCaseInfo, read_case_yaml(folder / CASE_FILE), folder, CASE_FILE)
    name_key = field_rules.record_name_field().key
    expected = read_expected_extraction(folder, name_key)
    seeded = read_seeded_errors(folder)
    documents = list_documents(folder)
    fake_folder = folder / FAKE_LLM_FOLDER
    # A mismatch means the labels may be out of date; the case still runs
    has_mismatch = info.field_rules_version != field_rules.version
    return EvalCase(
        folder=folder,
        info=info,
        expected=expected,
        seeded=seeded,
        documents=documents,
        fake_llm_folder=fake_folder if fake_folder.is_dir() else None,
        has_field_rules_mismatch=has_mismatch,
        warnings=find_case_warnings(info, expected, seeded, field_rules),
    )


def read_case_yaml(path: Path) -> Any:
    """Read a case's YAML file, turning a missing or broken file into a CaseLoadError."""
    try:
        return read_yaml(path)
    except ConfigError as error:
        raise CaseLoadError(describe_case_problems(path.parent, error.problems)) from error


def read_case_json(path: Path) -> Any:
    """Read a case's JSON file, turning a missing or broken file into a CaseLoadError."""
    if not path.is_file():
        raise CaseLoadError(f"Case {path.parent.name}: {path.name} is missing. Add it.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        problem = f"{path.name} is not valid JSON ({error})"
        raise CaseLoadError(describe_case_problems(path.parent, [problem])) from error


def read_case_model[ModelT: BaseModel](
    model: type[ModelT], data: Any, folder: Path, file_name: str
) -> ModelT:
    """Validate a case file's data against its model; problems name the case and the file."""
    try:
        return parse_model(model, data, file_name)
    except ConfigError as error:
        raise CaseLoadError(describe_case_problems(folder, error.problems)) from error


def describe_case_problems(folder: Path, problems: list[str]) -> str:
    """Join a case's problems into one plain message that says what to do."""
    lines = "; ".join(problems)
    return f"Case {folder.name} cannot be loaded: {lines}. Fix the case files and run again."


def read_expected_extraction(folder: Path, name_key: str) -> ExpectedExtraction:
    """Read `expected_extraction.json`; each record's name sits under the record name field key."""
    data = read_case_json(folder / EXPECTED_FILE)
    raw = read_case_model(RawExpectedExtraction, data, folder, EXPECTED_FILE)
    # Each record's name is moved from the name field's key to `name`
    records = [read_expected_record(record, name_key, folder) for record in raw.records]
    return ExpectedExtraction(records=records, excluded_items=raw.excluded_items)


def read_expected_record(raw: dict[str, Any], name_key: str, folder: Path) -> ExpectedRecord:
    """Read one expected record, taking its name from the record name field's key."""
    if not isinstance(raw.get(name_key), str):
        problem = f"{EXPECTED_FILE}: every record needs its name under '{name_key}'"
        raise CaseLoadError(describe_case_problems(folder, [problem]))
    record = dict(raw)
    record["name"] = record.pop(name_key)
    expected = read_case_model(ExpectedRecord, record, folder, EXPECTED_FILE)
    # The labeled name is also the name field's expected value, so it is scored like any field
    if name_key not in expected.fields:
        expected.fields[name_key] = ExpectedField(status="found", value=expected.name)
    return expected


def read_seeded_errors(folder: Path) -> SeededErrors:
    """Read `seeded_errors.json` if the case has one; no file means no seeded errors."""
    path = folder / SEEDED_FILE
    if not path.is_file():
        return SeededErrors()
    return read_case_model(SeededErrors, read_case_json(path), folder, SEEDED_FILE)


def list_documents(folder: Path) -> list[Path]:
    """Return the case's documents in name order (their upload order); there must be one."""
    documents_folder = folder / DOCUMENTS_FOLDER
    documents = (
        sorted(
            path
            for path in documents_folder.iterdir()
            if path.is_file() and not path.name.startswith(SKIPPED_PREFIXES)
        )
        if documents_folder.is_dir()
        else []
    )
    if not documents:
        problem = f"the '{DOCUMENTS_FOLDER}' folder has no documents"
        raise CaseLoadError(describe_case_problems(folder, [problem]))
    return documents


def find_case_warnings(
    info: EvalCaseInfo,
    expected: ExpectedExtraction,
    seeded: SeededErrors,
    field_rules: FieldRules,
) -> list[str]:
    """Return warnings: other field rules version, unknown field keys, repeated record names."""
    warnings: list[str] = []
    # Labels made against other field rules may no longer fit the fields
    if info.field_rules_version != field_rules.version:
        warnings.append(
            f"The case was labeled against field rules {info.field_rules_version}, but the "
            f"current field rules are {field_rules.version}. Check the expected output and "
            "relabel it if needed."
        )
    extracted_keys = {rule.key for rule in field_rules.extracted_fields()}
    # Field keys the current rules do not extract cannot be scored
    for record in expected.records:
        for key in sorted(set(record.fields) - extracted_keys):
            warnings.append(
                f"Expected record '{record.name}': field '{key}' is not an extracted field in "
                "the current field rules, so it is not scored. Fix or remove the label."
            )
    for error in seeded.errors:
        if error.field not in extracted_keys:
            warnings.append(
                f"Seeded error on '{error.record}': field '{error.field}' is not an extracted "
                "field, so it cannot be planted. Fix the seeded error."
            )
    # Records are matched by normalized name, so two expected records must not share one
    names = [normalize_for_match(record.name) for record in expected.records]
    if len(set(names)) != len(names):
        warnings.append(
            "Two expected records have the same name (ignoring case and spaces); only the "
            "first can be matched. Give each record its own name."
        )
    return warnings
