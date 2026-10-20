"""API tests for the admin routes: admin role required, lookup lists and reference data versions.

Uploads are the downloaded seed workbook and a synthetic CSV; column names come from the config.
"""

import csv
from io import StringIO
from pathlib import Path

import pytest

from app.config.bundle import ConfigBundle
from tests.fixtures.make_documents import WORD_FILE
from tests.integration.api_helpers import (
    XLSX_TYPE,
    assert_error,
    happy_replies,
    make_settings,
    open_api,
    read_file,
)

pytestmark = pytest.mark.usefixtures("blank_environment")

# Every admin route (method, path)
ADMIN_ROUTES = [
    ("GET", "/admin/lookup-lists/current"),
    ("POST", "/admin/lookup-lists"),
    ("POST", "/admin/lookup-lists/upl_0001/apply"),
    ("GET", "/admin/lookup-lists/versions"),
    ("GET", "/admin/lookup-lists/versions/v1/download"),
    ("POST", "/admin/reference-data"),
    ("POST", "/admin/reference-data/upl_0001/apply"),
    ("GET", "/admin/reference-data/versions"),
]


def make_reference_csv(bundle: ConfigBundle) -> bytes:
    """Return a synthetic existing-types CSV with the mapping's name and version columns."""
    columns = bundle.reference_mapping.columns
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow([columns.name, columns.version])
    writer.writerow(["Synthetic Existing A", "1"])
    return buffer.getvalue().encode("utf-8")


@pytest.mark.parametrize(("method", "path"), ADMIN_ROUTES)
def test_admin_routes_refuse_a_non_admin_user(tmp_path: Path, method: str, path: str) -> None:
    """A user without the admin role gets 403 on every admin route."""
    with open_api(make_settings(tmp_path, pilot_user_roles="user")) as api:
        response = api.client.request(method, path)
        error = assert_error(response, 403, "FORBIDDEN")
    assert "admin" in error["message"]


def test_lookup_lists_download_upload_apply_and_history(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """The current workbook uploads back as pending, applies as v1, and new runs use it."""
    with open_api(make_settings(tmp_path), happy_replies(bundle)) as api:
        client = api.client
        current = client.get("/admin/lookup-lists/current")
        assert current.status_code == 200
        assert current.headers["content-type"] == XLSX_TYPE
        assert bundle.lookup_lists.version in current.headers["content-disposition"]
        upload = client.post(
            "/admin/lookup-lists", files={"file": ("lookup_lists.xlsx", current.content, XLSX_TYPE)}
        ).json()
        assert upload["report"]["problems"] == []
        assert upload["version"]["upload_id"] == "upl_0001"
        assert upload["version"]["file_name"] == "lookup_lists.xlsx"
        assert "file_ref" not in upload["version"]
        applied = client.post("/admin/lookup-lists/upl_0001/apply").json()
        assert applied["version_id"] == "v1"
        assert applied["status"] == "current"
        history = client.get("/admin/lookup-lists/versions").json()
        assert history["current_version"] == "v1"
        assert len(history["versions"]) == 1
        assert client.get("/admin/lookup-lists/versions/v1/download").status_code == 200
        assert_error(client.post("/admin/lookup-lists/v1/apply"), 409, "VERSION_ALREADY_CURRENT")
        assert_error(client.post("/admin/lookup-lists/v9/apply"), 404, "VERSION_NOT_FOUND")
        # A new run captures the version that is current when it starts
        api.start_run([read_file(synthetic_documents, WORD_FILE)])
        run = client.get("/runs/run_0001").json()
        assert run["config_versions"]["lookup_lists"] == "v1"


def test_reference_data_upload_apply_and_history(tmp_path: Path, bundle: ConfigBundle) -> None:
    """A good reference data upload becomes pending, then current as v1."""
    with open_api(make_settings(tmp_path)) as api:
        client = api.client
        empty = client.get("/admin/reference-data/versions").json()
        assert empty == {"current_version": None, "versions": []}
        upload = client.post(
            "/admin/reference-data",
            files={"file": ("synthetic existing.csv", make_reference_csv(bundle), "text/csv")},
        ).json()
        assert upload["report"]["problems"] == []
        assert upload["report"]["row_count"] == 1
        applied = client.post("/admin/reference-data/upl_0001/apply").json()
        assert applied["version_id"] == "v1"
        history = client.get("/admin/reference-data/versions").json()
        assert history["current_version"] == "v1"
        [version] = history["versions"]
        assert version["file_name"] == "synthetic existing.csv"
        assert "file_ref" not in version
        assert "original_file" not in version["summary"]
