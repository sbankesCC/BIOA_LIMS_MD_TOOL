"""API tests for the OpenAPI review additions: page images, run fields, interrupted runs.

Also checks that responses never hold storage paths. Every document and value is synthetic.
"""

from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.config.bundle import ConfigBundle
from app.main import create_app
from app.storage.review_db import ReviewDatabase
from app.storage.run_store import RunStore
from app.transform.lookup_matching import BOOLEAN_VALUES
from tests.fixtures.fake_llm import TABLE_CHUNK_ID
from tests.fixtures.make_documents import SCANNED_PDF_FILE, WORD_FILE
from tests.integration.api_helpers import (
    XLSX_TYPE,
    ApiHarness,
    assert_error,
    happy_replies,
    make_settings,
    open_api,
    read_file,
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
ADDED_LOOKUP_VALUE = "Synthetic added value"

# Response keys that would hold a storage path (internal models only)
STORAGE_PATH_KEYS = {"file_ref", "loader_file", "audit_file", "image_ref", "upload_ref"}

pytestmark = pytest.mark.usefixtures("blank_environment")


def find_page_image_chunk_id(storage_dir: Path) -> str:
    """Return the ID of the first scanned-page chunk of run_0001, read from the run store."""
    chunks = RunStore(storage_dir).open_run("run_0001").read_chunks()
    return next(chunk.chunk_id for chunk in chunks if chunk.kind == "page_image")


def find_keys(data: Any) -> set[str]:
    """Return every object key anywhere in a JSON value."""
    if isinstance(data, dict):
        keys = set(data)
        for value in data.values():
            keys |= find_keys(value)
        return keys
    if isinstance(data, list):
        return set().union(*(find_keys(item) for item in data)) if data else set()
    return set()


def add_lookup_value(api: ApiHarness, sheet_name: str) -> None:
    """Upload the current lookup workbook with one value added, and apply it as v1."""
    current = api.client.get("/admin/lookup-lists/current").content
    workbook = load_workbook(BytesIO(current))
    workbook[sheet_name].append([ADDED_LOOKUP_VALUE])
    content = BytesIO()
    workbook.save(content)
    upload = api.client.post(
        "/admin/lookup-lists", files={"file": ("lookup_lists.xlsx", content.getvalue(), XLSX_TYPE)}
    )
    assert upload.json()["report"]["problems"] == [], upload.text
    assert api.client.post("/admin/lookup-lists/upl_0001/apply").status_code == 200


# ----- Page images -----


def test_page_image_is_served_for_a_scanned_page(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """A scanned page's PNG is served; an unknown chunk and a text chunk are 404."""
    files = [
        read_file(synthetic_documents, WORD_FILE),
        read_file(synthetic_documents, SCANNED_PDF_FILE),
    ]
    settings = make_settings(tmp_path)
    with open_api(settings, happy_replies(bundle)) as api:
        api.start_run(files)
        chunk_id = find_page_image_chunk_id(tmp_path / "storage")
        image = api.client.get(f"/runs/run_0001/chunks/{chunk_id}/image")
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"
        assert image.content.startswith(PNG_SIGNATURE)
        unknown = api.client.get("/runs/run_0001/chunks/doc09-p01-c001/image")
        assert_error(unknown, 404, "CHUNK_NOT_FOUND")
        text_chunk = api.client.get(f"/runs/run_0001/chunks/{TABLE_CHUNK_ID}/image")
        error = assert_error(text_chunk, 404, "PAGE_IMAGE_NOT_FOUND")
        assert str(tmp_path) not in error["message"]
        assert_error(
            api.client.get(f"/runs/run_9999/chunks/{chunk_id}/image"), 404, "RUN_NOT_FOUND"
        )


# ----- Run fields -----


def test_run_fields_follow_the_field_rules_and_the_run_lookup_version(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """Fields come in loader order; list values stay the run's own version after an admin apply."""
    rules = bundle.field_rules.fields
    list_rule = next(rule for rule in rules if rule.lookup_sheet is not None)
    sheet = list_rule.lookup_sheet or ""
    with open_api(make_settings(tmp_path), happy_replies(bundle)) as api:
        api.start_run([read_file(synthetic_documents, WORD_FILE)])
        add_lookup_value(api, sheet)
        old_run = api.client.get("/runs/run_0001/fields").json()
        api.start_run([read_file(synthetic_documents, WORD_FILE)])
        new_run = api.client.get("/runs/run_0002/fields").json()
        assert_error(api.client.get("/runs/run_9999/fields"), 404, "RUN_NOT_FOUND")
    # Count and order match the field rules
    assert [field["key"] for field in old_run["fields"]] == [rule.key for rule in rules]
    assert old_run["field_rules_version"] == bundle.field_rules.version
    # The older run keeps the lookup version it captured; the new run gets v1
    old_field = next(field for field in old_run["fields"] if field["key"] == list_rule.key)
    new_field = next(field for field in new_run["fields"] if field["key"] == list_rule.key)
    assert old_run["lookup_lists_version"] == bundle.lookup_lists.version
    assert old_field["allowed_values"] == bundle.lookup_lists.sheets[sheet]
    assert new_run["lookup_lists_version"] == "v1"
    assert new_field["allowed_values"] == [*bundle.lookup_lists.sheets[sheet], ADDED_LOOKUP_VALUE]


def test_run_fields_give_boolean_values_and_none_for_free_fields(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """Boolean fields offer the values validation accepts; other non-list fields offer none."""
    with open_api(make_settings(tmp_path), happy_replies(bundle)) as api:
        api.start_run([read_file(synthetic_documents, WORD_FILE)])
        fields = api.client.get("/runs/run_0001/fields").json()["fields"]
    rules = {rule.key: rule for rule in bundle.field_rules.fields}
    booleans = [field for field in fields if field["is_boolean"]]
    assert booleans
    for field in fields:
        rule = rules[field["key"]]
        assert field["column"] == rule.column
        assert field["has_lookup_list"] == (rule.lookup_sheet is not None)
        if field["is_boolean"]:
            assert field["allowed_values"] == list(BOOLEAN_VALUES)
        elif not field["has_lookup_list"]:
            assert field["allowed_values"] == []


# ----- Interrupted runs -----


def test_startup_fails_an_interrupted_run_and_it_can_be_retried(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """A run left processing when the app stopped is failed at start, with a run issue."""
    settings = make_settings(tmp_path)
    with open_api(settings, happy_replies(bundle)) as api:
        api.start_run([read_file(synthetic_documents, WORD_FILE)])
    # Put the run back in a processing status, as if the app stopped midway
    database = ReviewDatabase(tmp_path / "review.sqlite")
    database.set_run_status("run_0001", "extracting")
    database.close()
    with open_api(settings, happy_replies(bundle)) as api:
        run = api.client.get("/runs/run_0001").json()
        assert run["status"] == "failed"
        assert run["current_step"] is None
        [issue] = [i for i in run["run_issues"] if i["code"] == "PROCESSING_INTERRUPTED"]
        assert issue["severity"] == "error"
        retry = api.client.post("/runs/run_0001/retry")
        api.runner.wait_for_all()
        assert retry.status_code == 202, retry.text
        assert api.client.get("/runs/run_0002").json()["status"] == "in_review"


def test_app_starts_with_config_but_no_review_db(tmp_path: Path) -> None:
    """With REVIEW_DB blank, the start-up check is skipped and the app still starts."""
    settings = make_settings(tmp_path, review_db=None)
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
        assert_error(client.get("/runs"), 503, "SETTING_MISSING")


# ----- No storage paths -----


def test_responses_name_files_but_never_storage_paths(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """Exports and versions show file names; no response or schema property holds a path."""
    with open_api(make_settings(tmp_path), happy_replies(bundle)) as api:
        api.start_run([read_file(synthetic_documents, WORD_FILE)])
        export = api.client.post("/runs/run_0001/exports").json()
        responses = [
            export,
            api.client.get("/runs/run_0001").json(),
            api.client.get("/runs/run_0001/exports").json(),
            api.client.get("/admin/lookup-lists/versions").json(),
        ]
        schema = api.client.get("/openapi.json").json()
    assert export["loader_file_name"].endswith(".xlsx")
    assert "/" not in export["loader_file_name"]
    assert "/" not in export["audit_file_name"]
    for body in responses:
        assert not find_keys(body) & STORAGE_PATH_KEYS
    for component in schema["components"]["schemas"].values():
        assert not set(component.get("properties", {})) & STORAGE_PATH_KEYS
