"""Reference data admin (ARCHITECTURE §4.12): uploads of existing Consumable Types, versioned.

An `.xlsx` or `.csv` export is read with the column names in `reference_data_mapping.yaml`,
checked, and stored as a snapshot (`ReferenceData`) under `STORAGE_DIR/reference_data/`.
Validation uses the current snapshot; a run keeps the version it started with.
"""

import csv
from collections.abc import Sequence
from datetime import datetime
from io import StringIO
from pathlib import Path

from pydantic import BaseModel, JsonValue

from app.admin.lookup_checks import open_workbook
from app.admin.reports import UploadFinding, make_problem, make_warning
from app.admin.versions import (
    apply_version,
    find_version,
    make_admin_event,
    make_file_ref,
    next_upload_id,
    resolve_file_ref,
)
from app.config.reference_mapping import ReferenceColumns, ReferenceMapping
from app.contracts.reference import ReferenceData, ReferenceType
from app.ids import format_numbered_id
from app.ingest.xlsx import format_cell
from app.logging_setup import log_event
from app.storage.review_db import DataVersion, DataVersionKind, ReviewDatabase

REFERENCE_FOLDER = "reference_data"
SNAPSHOT_FILE = "snapshot.json"
ORIGINAL_FILE_STEM = "original"
KIND: DataVersionKind = "reference"
CANDIDATE_PREFIX = "ref_"
ACCEPTED_SUFFIXES = (".xlsx", ".csv")

# Excel saves CSV files with a byte order mark; this encoding reads files with or without one
CSV_ENCODING = "utf-8-sig"

# Mapping keys every upload must have (the others are optional)
REQUIRED_KEYS = ("name", "version")

# Finding codes
UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
FILE_UNREADABLE = "FILE_UNREADABLE"
NO_ROWS = "NO_ROWS"
MISSING_COLUMN = "MISSING_COLUMN"
OPTIONAL_COLUMN_MISSING = "OPTIONAL_COLUMN_MISSING"
BLANK_REQUIRED_VALUE = "BLANK_REQUIRED_VALUE"

# Admin events (admin_events table)
UPLOADED_EVENT = "reference_data_uploaded"
APPLIED_EVENT = "reference_data_applied"
RESTORED_EVENT = "reference_data_restored"

# A table row: its row number in the file and its cells as text
NumberedRow = tuple[int, list[str]]


class ReferenceUploadReport(BaseModel):
    """The check report of one upload: rows read, passed checks, problems and warnings."""

    file_name: str
    row_count: int
    passed_checks: list[str]
    problems: list[UploadFinding]
    warnings: list[UploadFinding]

    def has_problems(self) -> bool:
        """Return True if any problem blocks applying this upload."""
        return bool(self.problems)


class ReferenceCheckResult(BaseModel):
    """The report, plus the existing types read when no problem was found."""

    report: ReferenceUploadReport
    types: list[ReferenceType] | None


class ReferenceUploadResult(BaseModel):
    """An upload's check report, and the pending version created when it has no problems."""

    report: ReferenceUploadReport
    version: DataVersion | None


# ----- Checks -----


def check_reference_upload(
    file_name: str, content: bytes, columns: ReferenceColumns
) -> ReferenceCheckResult:
    """Read an uploaded export and check its columns and required values."""
    rows, findings = read_upload_rows(file_name, content)
    types: list[ReferenceType] = []
    if rows:
        positions = {cell.strip(): index for index, cell in enumerate(rows[0][1]) if cell.strip()}
        findings += check_columns(positions, columns)
        if not any(finding.severity == "problem" for finding in findings):
            types, row_findings = read_types(rows[1:], positions, columns)
            findings += row_findings
            if not types:
                message = "The file has a header row but no existing Consumable Types under it."
                findings.append(make_problem(NO_ROWS, message))
    report = build_report(file_name, len(types), findings)
    return ReferenceCheckResult(report=report, types=None if report.has_problems() else types)


def read_upload_rows(
    file_name: str, content: bytes
) -> tuple[list[NumberedRow], list[UploadFinding]]:
    """Return the file's non-blank rows (header first), or a problem saying why there are none."""
    suffix = Path(file_name).suffix.lower()
    if suffix not in ACCEPTED_SUFFIXES:
        message = "Upload the export as an Excel workbook (.xlsx) or a CSV file (.csv)."
        return [], [make_problem(UNSUPPORTED_FILE_TYPE, message)]
    table = read_csv(content) if suffix == ".csv" else read_xlsx(content)
    if table is None:
        message = f"The file could not be read as {suffix}. Export it again and upload it."
        return [], [make_problem(FILE_UNREADABLE, message)]
    # Blank rows are skipped; row numbers stay as in the file
    rows = [
        (number, row) for number, row in enumerate(table, start=1) if any(c.strip() for c in row)
    ]
    if not rows:
        return [], [make_problem(NO_ROWS, "The file is empty. Export it again and upload it.")]
    return rows, []


def read_csv(content: bytes) -> list[list[str]] | None:
    """Return a CSV file's rows as text, or None if it cannot be decoded."""
    try:
        return list(csv.reader(StringIO(content.decode(CSV_ENCODING))))
    except (UnicodeDecodeError, csv.Error):
        return None


def read_xlsx(content: bytes) -> list[list[str]] | None:
    """Return the first sheet's rows as text, or None if the workbook cannot be read."""
    workbook = open_workbook(content)
    if workbook is None:
        return None
    sheet = workbook.worksheets[0]
    return [[format_cell(cell) for cell in row] for row in sheet.iter_rows(values_only=True)]


def check_columns(positions: dict[str, int], columns: ReferenceColumns) -> list[UploadFinding]:
    """Return a problem per missing required column and a warning per missing optional one."""
    findings: list[UploadFinding] = []
    for key, column in mapped_columns(columns).items():
        if column in positions:
            continue
        if key in REQUIRED_KEYS:
            message = (
                f"The column '{column}' is missing. It holds the {key.replace('_', ' ')} of each "
                "existing type. Export the file again with this column, or ask a developer to "
                "update the column mapping."
            )
            findings.append(make_problem(MISSING_COLUMN, message, row=1))
        else:
            message = f"The optional column '{column}' is missing. The upload works without it."
            findings.append(make_warning(OPTIONAL_COLUMN_MISSING, message, row=1))
    return findings


def mapped_columns(columns: ReferenceColumns) -> dict[str, str]:
    """Return the column name for each mapping key that has one."""
    return {key: column for key, column in columns.model_dump().items() if column}


def read_types(
    rows: Sequence[NumberedRow], positions: dict[str, int], columns: ReferenceColumns
) -> tuple[list[ReferenceType], list[UploadFinding]]:
    """Build one existing type per row; a row missing a required value is a problem."""
    mapping = mapped_columns(columns)
    types: list[ReferenceType] = []
    findings: list[UploadFinding] = []
    for number, row in rows:
        values = {
            key: read_value(row, positions[column])
            for key, column in mapping.items()
            if column in positions
        }
        missing = [mapping[key] for key in REQUIRED_KEYS if values.get(key) is None]
        for column in missing:
            message = f"Row {number} has no value in '{column}'. Fill it in or delete the row."
            findings.append(make_problem(BLANK_REQUIRED_VALUE, message, row=number))
        if not missing:
            candidate_id = format_numbered_id(CANDIDATE_PREFIX, len(types) + 1)
            types.append(ReferenceType.model_validate({"candidate_id": candidate_id, **values}))
    return types, findings


def read_value(row: Sequence[str], index: int) -> str | None:
    """Return one cell as written, or None when it is missing or blank."""
    if index >= len(row) or not row[index].strip():
        return None
    return row[index]


def build_report(
    file_name: str, row_count: int, findings: Sequence[UploadFinding]
) -> ReferenceUploadReport:
    """Sort the findings into problems and warnings and list the checks that passed."""
    problems = [finding for finding in findings if finding.severity == "problem"]
    passed: list[str] = []
    if not problems:
        passed = ["All required columns present", f"{row_count} existing Consumable Types read"]
    return ReferenceUploadReport(
        file_name=file_name,
        row_count=row_count,
        passed_checks=passed,
        problems=problems,
        warnings=[finding for finding in findings if finding.severity == "warning"],
    )


# ----- Versions -----


class ReferenceDataAdmin:
    """Reference data versions: admin uploads of existing Consumable Types."""

    def __init__(
        self, database: ReviewDatabase, storage_dir: Path, mapping: ReferenceMapping
    ) -> None:
        """Use the review database, STORAGE_DIR and the column mapping from the client config."""
        self.database = database
        self.storage_dir = storage_dir
        self.mapping = mapping

    def find_current_reference_data(self) -> ReferenceData | None:
        """Return the reference data a new run uses, or None if none was ever applied."""
        current = self.database.read_current_data_version(KIND)
        return None if current is None else self.load_version(current)

    def load_reference_data(self, version_id: str | None) -> ReferenceData | None:
        """Return one version's snapshot (e.g. a run's captured version); None gives None."""
        if version_id is None:
            return None
        return self.load_version(find_version(self.database, KIND, version_id))

    def load_version(self, version: DataVersion) -> ReferenceData:
        """Load a stored snapshot; its version name comes from the database."""
        path = resolve_file_ref(self.storage_dir, version.file_ref)
        snapshot = ReferenceData.model_validate_json(path.read_bytes())
        return snapshot.model_copy(update={"version": version.version_id or version.upload_id})

    def list_versions(self) -> list[DataVersion]:
        """Return every upload in upload order."""
        return self.database.list_data_versions(KIND)

    def upload(
        self, file_name: str, content: bytes, user: str, at: datetime
    ) -> ReferenceUploadResult:
        """Check an uploaded export; without problems it is stored as a pending version."""
        result = check_reference_upload(file_name, content, self.mapping.columns)
        version = None
        if result.types is not None:
            version = self.store_upload(file_name, content, result, user, at)
        event = make_admin_event(
            UPLOADED_EVENT,
            user,
            at,
            upload_id=version.upload_id if version is not None else None,
            file_name=file_name,
            problems=len(result.report.problems),
            warnings=len(result.report.warnings),
        )
        self.database.add_admin_event(event)
        return ReferenceUploadResult(report=result.report, version=version)

    def store_upload(
        self, file_name: str, content: bytes, result: ReferenceCheckResult, user: str, at: datetime
    ) -> DataVersion:
        """Save the original file and the snapshot under STORAGE_DIR; add the pending row."""
        with self.database.transaction():
            upload_id = next_upload_id(self.list_versions())
            folder = self.storage_dir / REFERENCE_FOLDER / upload_id
            folder.mkdir(parents=True, exist_ok=True)
            original = folder / f"{ORIGINAL_FILE_STEM}{Path(file_name).suffix.lower()}"
            original.write_bytes(content)
            snapshot = folder / SNAPSHOT_FILE
            data = ReferenceData(version=upload_id, types=result.types or [])
            snapshot.write_text(data.model_dump_json(indent=2), encoding="utf-8")
            version = DataVersion(
                upload_id=upload_id,
                file_ref=make_file_ref(self.storage_dir, snapshot),
                uploaded_by=user,
                uploaded_at=at,
                summary=summarize_upload(result.report),
            )
            self.database.add_data_version(KIND, version)
        return version

    def apply_version(self, name: str, user: str, at: datetime) -> DataVersion:
        """Make a pending upload current as the next `vN`, or restore an older version."""
        with self.database.transaction():
            version = find_version(self.database, KIND, name)
            applied = apply_version(self.database, KIND, version, user, at)
            event_name = RESTORED_EVENT if applied.is_restore else APPLIED_EVENT
            event = make_admin_event(
                event_name,
                user,
                at,
                upload_id=applied.version.upload_id,
                version_id=applied.version.version_id,
            )
            self.database.add_admin_event(event)
        log_event("reference_data_applied")
        return applied.version


def summarize_upload(report: ReferenceUploadReport) -> dict[str, JsonValue]:
    """Return what the version history shows: file name, row count and report (no paths)."""
    return {
        "file_name": report.file_name,
        "row_count": report.row_count,
        "report": report.model_dump(mode="json"),
    }
