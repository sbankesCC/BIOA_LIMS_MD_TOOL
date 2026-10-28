"""API tests for runs and errors, all with the one error shape.

Upload checks and limits, retry, rename, sign-in settings, not-found and conflict answers.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config.bundle import ConfigBundle
from app.main import create_app
from app.settings import Settings
from tests.fixtures.fake_llm import extraction_reply, unsupported_name, verification_reply
from tests.fixtures.make_documents import BROKEN_FILE, WORD_FILE
from tests.integration.api_helpers import (
    CHANGE_TIME,
    TWO_ROWS,
    assert_error,
    happy_replies,
    make_settings,
    open_api,
    read_file,
)

# A synthetic upload just over one megabyte (MAX_FILE_SIZE_MB is in whole megabytes)
BIG_FILE = ("synthetic_big.pdf", b"x" * (1024 * 1024 + 1))

pytestmark = pytest.mark.usefixtures("blank_environment")


def test_app_builds_with_every_setting_blank() -> None:
    """With nothing set the app starts, serves its schema, and run routes name a setting."""
    with TestClient(create_app(Settings(_env_file=None))) as client:  # pyright: ignore[reportCallIssue]
        assert client.get("/health").status_code == 200
        assert client.get("/openapi.json").status_code == 200
        error = assert_error(client.get("/runs"), 503, "SETTING_MISSING")
    assert "PILOT_USER" in error["message"]


def test_missing_pilot_user_names_the_setting(tmp_path: Path) -> None:
    """A blank PILOT_USER gives a plain error that says which setting to fill in."""
    with open_api(make_settings(tmp_path, pilot_user=None)) as api:
        error = assert_error(api.client.get("/runs"), 503, "SETTING_MISSING")
    assert error["details"] == {"setting": "PILOT_USER"}
    assert error["message"] == "Set PILOT_USER in .env, then restart the app."


def test_user_without_a_known_role_is_403(tmp_path: Path) -> None:
    """A signed-in user with neither the user nor the admin role is refused."""
    with open_api(make_settings(tmp_path, pilot_user_roles="viewer")) as api:
        assert_error(api.client.get("/runs"), 403, "FORBIDDEN")


def test_rejected_extension_is_400_and_stores_nothing(tmp_path: Path) -> None:
    """A file type other than .docx, .pdf or .xlsx is refused before anything is stored."""
    with open_api(make_settings(tmp_path)) as api:
        response = api.start_run([("synthetic notes.txt", b"synthetic")])
        error = assert_error(response, 400, "FILE_REJECTED")
        assert "synthetic notes.txt" in error["message"]
        assert api.client.get("/runs").json() == []


def test_too_many_files_is_413_when_limit_is_set(
    tmp_path: Path, synthetic_documents: dict[str, Path]
) -> None:
    """More files than MAX_FILES_PER_RUN are refused with 413."""
    files = [read_file(synthetic_documents, WORD_FILE), read_file(synthetic_documents, BROKEN_FILE)]
    with open_api(make_settings(tmp_path, max_files_per_run=1)) as api:
        error = assert_error(api.start_run(files), 413, "TOO_MANY_FILES")
        assert error["details"] == {"file_count": 2, "limit": 1}
        assert api.client.get("/runs").json() == []


def test_large_file_is_413_when_limit_is_set(tmp_path: Path) -> None:
    """A file over MAX_FILE_SIZE_MB is refused with 413."""
    with open_api(make_settings(tmp_path, max_file_size_mb=1)) as api:
        assert_error(api.start_run([BIG_FILE]), 413, "FILE_TOO_LARGE")


def test_large_file_is_accepted_when_limit_is_blank(tmp_path: Path) -> None:
    """With MAX_FILE_SIZE_MB blank there is no size limit."""
    with open_api(make_settings(tmp_path)) as api:
        response = api.start_run([BIG_FILE])
        assert response.status_code == 202, response.text


def test_retry_starts_a_linked_run_and_keeps_the_failed_one(
    tmp_path: Path, synthetic_documents: dict[str, Path]
) -> None:
    """Retrying a failed run starts a new run from the same files with `retry_of` set."""
    with open_api(make_settings(tmp_path)) as api:
        api.start_run([read_file(synthetic_documents, BROKEN_FILE)])
        failed = api.client.get("/runs/run_0001").json()
        assert failed["status"] == "failed"
        assert [issue["code"] for issue in failed["run_issues"]] == [
            "FILE_UNREADABLE",
            "NO_READABLE_DOCUMENTS",
        ]
        response = api.client.post("/runs/run_0001/retry")
        api.runner.wait_for_all()
        assert response.status_code == 202, response.text
        assert response.json() == {"run_id": "run_0002", "retry_of": "run_0001"}
        retried = api.client.get("/runs/run_0002").json()
        assert retried["retry_of"] == "run_0001"
        assert [d["file_name"] for d in retried["documents"]] == [BROKEN_FILE]
        assert api.client.get("/runs/run_0001").json() == failed


def test_retry_of_a_run_that_did_not_fail_is_409(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """Only failed runs can be retried."""
    with open_api(make_settings(tmp_path), happy_replies(bundle)) as api:
        api.start_run([read_file(synthetic_documents, WORD_FILE)])
        assert_error(api.client.post("/runs/run_0001/retry"), 409, "RUN_NOT_FAILED")


def test_changes_on_a_failed_run_are_409(
    tmp_path: Path, synthetic_documents: dict[str, Path]
) -> None:
    """A run that is not in review cannot take changes."""
    with open_api(make_settings(tmp_path)) as api:
        api.start_run([read_file(synthetic_documents, BROKEN_FILE)])
        change = {"type": "restore_record", "change_id": "chg_0001", "record_id": "rec_0001"}
        response = api.post_changes("run_0001", [change])
        assert_error(response, 409, "RUN_NOT_IN_REVIEW")


def test_rename_changes_the_name_and_refuses_a_blank_one(
    tmp_path: Path, synthetic_documents: dict[str, Path]
) -> None:
    """PATCH renames the run; a blank name fails validation with the error shape."""
    with open_api(make_settings(tmp_path)) as api:
        api.start_run([read_file(synthetic_documents, BROKEN_FILE)])
        renamed = api.client.patch("/runs/run_0001", json={"name": "  synthetic renamed  "})
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["name"] == "synthetic renamed"
        error = assert_error(
            api.client.patch("/runs/run_0001", json={"name": " "}), 422, "VALIDATION_FAILED"
        )
        assert error["details"]["problems"][0]["location"] == ["body", "name"]


def test_unknown_run_record_chunk_and_export_are_404(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """Unknown IDs give 404 with a code naming what was not found."""
    with open_api(make_settings(tmp_path), happy_replies(bundle)) as api:
        assert_error(api.client.get("/runs/run_9999"), 404, "RUN_NOT_FOUND")
        api.start_run([read_file(synthetic_documents, WORD_FILE)])
        client = api.client
        assert_error(client.get("/runs/run_0001/records/rec_9999"), 404, "RECORD_NOT_FOUND")
        assert_error(client.get("/runs/run_0001/chunks/doc09-c001"), 404, "CHUNK_NOT_FOUND")
        assert_error(client.get("/runs/run_0001/exports/exp_0009/audit"), 404, "EXPORT_NOT_FOUND")
        preview = client.get(
            "/runs/run_0001/bulk-preview", params={"mode": "change_all", "issue_id": "iss_unknown"}
        )
        assert_error(preview, 404, "ISSUE_NOT_FOUND")
        assert_error(client.get("/no-such-address"), 404, "NOT_FOUND")


def test_invalid_change_is_400_and_bad_body_is_422(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """A change breaking a §6 rule is 400; a body that does not parse is 422."""
    with open_api(make_settings(tmp_path), happy_replies(bundle)) as api:
        api.start_run([read_file(synthetic_documents, WORD_FILE)])
        change = {"type": "restore_record", "change_id": "chg_0001", "record_id": "rec_9999"}
        assert_error(api.post_changes("run_0001", [change]), 400, "CHANGE_INVALID")
        bad_body = {"user": "x", "timestamp": CHANGE_TIME, "changes": [{"type": "unknown"}]}
        response = api.client.post("/runs/run_0001/changes", json=bad_body)
        assert_error(response, 422, "VALIDATION_FAILED")


def test_bulk_preview_refuses_an_individual_review_issue(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """An individual-review warning (source may not support the value) is never bulk-changed."""
    replies = {
        "extraction": [extraction_reply(bundle.field_rules, TWO_ROWS)],
        "extraction_verification": [
            verification_reply([unsupported_name(bundle.field_rules, "rec_0001")])
        ],
    }
    # No re-extraction, so the finding becomes an issue on the first record's name
    with open_api(make_settings(tmp_path, max_reextract=0), replies) as api:
        api.start_run([read_file(synthetic_documents, WORD_FILE)])
        record = api.client.get("/runs/run_0001/records/rec_0001").json()
        issue = next(issue for issue in record["issues"] if issue["individual_review"])
        response = api.client.get(
            "/runs/run_0001/bulk-preview",
            params={"mode": "change_all", "issue_id": issue["issue_id"]},
        )
        assert_error(response, 409, "BULK_ACCEPT_NOT_ALLOWED")
