"""Reference data admin tests: .xlsx and .csv uploads, column checks, snapshot, apply, restore.

Column names come from the client's reference data mapping; every row is synthetic.
"""

import csv
from io import BytesIO, StringIO
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.admin import reference_data
from app.admin.errors import AdminError
from app.admin.reference_data import ReferenceDataAdmin
from app.config.bundle import ConfigBundle
from app.config.reference_mapping import ReferenceColumns
from app.storage.review_db import ReviewDatabase
from app.validation import codes
from tests.unit.review_helpers import NOW
from tests.unit.validation_helpers import issues_with_code, make_record, run_validation

ADMIN = "synthetic.admin"

# Synthetic existing types: name, version (a number, as Excel stores it), description
SYNTHETIC_ROWS: list[list[object]] = [
    ["Synthetic Existing A", 1, "synthetic description A"],
    ["Synthetic Existing B", 2, None],
]


@pytest.fixture
def admin(tmp_path: Path, bundle: ConfigBundle) -> ReferenceDataAdmin:
    """Return a reference data admin with a new review database and storage folder."""
    database = ReviewDatabase(tmp_path / "review.sqlite")
    return ReferenceDataAdmin(database, tmp_path / "storage", bundle.reference_mapping)


def make_header(columns: ReferenceColumns, leave_out: str | None = None) -> list[str]:
    """Return the name, version and description column names, minus one if asked."""
    names = [columns.name, columns.version, columns.description or "synthetic description"]
    return [name for name in names if name != leave_out]


def make_xlsx(header: list[str], rows: list[list[object]]) -> bytes:
    """Return a workbook with a header row and data rows on its first sheet."""
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(header)
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def make_csv(header: list[str], rows: list[list[object]]) -> bytes:
    """Return CSV bytes (UTF-8 with a byte order mark, as Excel saves it)."""
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows([["" if cell is None else cell for cell in row] for row in rows])
    return buffer.getvalue().encode("utf-8-sig")


def test_xlsx_upload_builds_a_snapshot(admin: ReferenceDataAdmin, bundle: ConfigBundle) -> None:
    """A good workbook passes, with one existing type per row and numbers read as text."""
    content = make_xlsx(make_header(bundle.reference_mapping.columns), SYNTHETIC_ROWS)
    result = admin.upload("synthetic export.xlsx", content, ADMIN, NOW)
    assert result.report.problems == []
    assert result.report.row_count == 2
    assert result.version is not None and result.version.status == "pending"
    snapshot = admin.load_version(result.version)
    assert [t.candidate_id for t in snapshot.types] == ["ref_0001", "ref_0002"]
    assert (snapshot.types[0].name, snapshot.types[0].version) == ("Synthetic Existing A", "1")
    assert (snapshot.types[0].description, snapshot.types[1].description) == (
        "synthetic description A",
        None,
    )


def test_csv_upload_is_accepted(admin: ReferenceDataAdmin, bundle: ConfigBundle) -> None:
    """A CSV export with the mapped columns passes the same way."""
    content = make_csv(make_header(bundle.reference_mapping.columns), SYNTHETIC_ROWS)
    result = admin.upload("synthetic export.csv", content, ADMIN, NOW)
    assert result.report.problems == []
    assert result.version is not None
    assert [t.name for t in admin.load_version(result.version).types] == [
        "Synthetic Existing A",
        "Synthetic Existing B",
    ]


def test_missing_required_column_is_a_problem(
    admin: ReferenceDataAdmin, bundle: ConfigBundle
) -> None:
    """Without the mapped name column the upload is rejected, naming the column."""
    columns = bundle.reference_mapping.columns
    header = make_header(columns, leave_out=columns.name)
    rows = [row[1:] for row in SYNTHETIC_ROWS]
    result = admin.upload("synthetic export.xlsx", make_xlsx(header, rows), ADMIN, NOW)
    assert [p.code for p in result.report.problems] == [reference_data.MISSING_COLUMN]
    assert columns.name in result.report.problems[0].message
    assert result.version is None
    assert admin.list_versions() == []


def test_missing_optional_column_is_a_warning(
    admin: ReferenceDataAdmin, bundle: ConfigBundle
) -> None:
    """Optional mapped columns that are missing give warnings; the upload passes."""
    columns = bundle.reference_mapping.columns
    header = [columns.name, columns.version]
    rows = [row[:2] for row in SYNTHETIC_ROWS]
    result = admin.upload("synthetic export.xlsx", make_xlsx(header, rows), ADMIN, NOW)
    optional = [
        key
        for key, value in columns.model_dump().items()
        if value and key not in reference_data.REQUIRED_KEYS
    ]
    assert len(result.report.warnings) == len(optional)
    assert {w.code for w in result.report.warnings} == {reference_data.OPTIONAL_COLUMN_MISSING}
    assert result.version is not None


def test_row_without_a_name_is_a_problem(admin: ReferenceDataAdmin, bundle: ConfigBundle) -> None:
    """A data row with no name is reported with its row number."""
    rows = [*SYNTHETIC_ROWS, [None, 3, "synthetic nameless"]]
    content = make_xlsx(make_header(bundle.reference_mapping.columns), rows)
    result = admin.upload("synthetic export.xlsx", content, ADMIN, NOW)
    assert [(p.code, p.row) for p in result.report.problems] == [
        (reference_data.BLANK_REQUIRED_VALUE, 4)
    ]
    assert result.version is None


@pytest.mark.parametrize(
    ("file_name", "content", "code"),
    [
        ("synthetic export.xls", b"synthetic", reference_data.UNSUPPORTED_FILE_TYPE),
        ("synthetic export.xlsx", b"synthetic, not a workbook", reference_data.FILE_UNREADABLE),
        ("synthetic export.csv", b"", reference_data.NO_ROWS),
    ],
    ids=["wrong type", "unreadable", "empty"],
)
def test_unusable_file_is_rejected(
    admin: ReferenceDataAdmin, file_name: str, content: bytes, code: str
) -> None:
    """Wrong file types, unreadable files and empty files give one plain problem."""
    result = admin.upload(file_name, content, ADMIN, NOW)
    assert [problem.code for problem in result.report.problems] == [code]
    assert result.version is None


def test_header_without_rows_is_rejected(admin: ReferenceDataAdmin, bundle: ConfigBundle) -> None:
    """A file with only the header row has no existing types to store."""
    content = make_csv(make_header(bundle.reference_mapping.columns), [])
    result = admin.upload("synthetic export.csv", content, ADMIN, NOW)
    assert [problem.code for problem in result.report.problems] == [reference_data.NO_ROWS]


def upload_and_apply(admin: ReferenceDataAdmin, bundle: ConfigBundle) -> str:
    """Upload the synthetic rows and apply them; return the version ID."""
    content = make_xlsx(make_header(bundle.reference_mapping.columns), SYNTHETIC_ROWS)
    result = admin.upload("synthetic export.xlsx", content, ADMIN, NOW)
    assert result.version is not None
    applied = admin.apply_version(result.version.upload_id, ADMIN, NOW)
    assert applied.version_id is not None
    return applied.version_id


def test_apply_and_restore_versions(admin: ReferenceDataAdmin, bundle: ConfigBundle) -> None:
    """No data before any apply; then v1, v2, and v1 restored; each action is logged."""
    assert admin.find_current_reference_data() is None
    assert upload_and_apply(admin, bundle) == "v1"
    assert upload_and_apply(admin, bundle) == "v2"
    current = admin.find_current_reference_data()
    assert current is not None and current.version == "v2"
    admin.apply_version("v1", ADMIN, NOW)
    restored = admin.find_current_reference_data()
    assert restored is not None and restored.version == "v1"
    assert admin.load_reference_data(None) is None
    loaded = admin.load_reference_data("v2")
    assert loaded is not None and loaded.version == "v2"
    events = [event.event for event in admin.database.read_admin_events()]
    assert events == [
        "reference_data_uploaded",
        "reference_data_applied",
        "reference_data_uploaded",
        "reference_data_applied",
        "reference_data_restored",
    ]


def test_apply_refuses_unknown_version(admin: ReferenceDataAdmin) -> None:
    """An unknown version gives VERSION_NOT_FOUND."""
    with pytest.raises(AdminError) as error:
        admin.apply_version("v7", ADMIN, NOW)
    assert error.value.code == "VERSION_NOT_FOUND"


def test_applied_snapshot_feeds_the_duplicate_check(
    admin: ReferenceDataAdmin, bundle: ConfigBundle
) -> None:
    """A record named like an existing type in the current snapshot gets EXISTS_IN_LABVANTAGE."""
    upload_and_apply(admin, bundle)
    reference = admin.find_current_reference_data()
    record = make_record(bundle, name=str(SYNTHETIC_ROWS[0][0]))
    result = run_validation(bundle, [record], reference=reference)
    assert len(issues_with_code(result, codes.EXISTS_IN_LABVANTAGE)) == 1
