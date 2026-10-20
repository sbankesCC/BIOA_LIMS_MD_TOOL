"""API tests for the 2026-10-21 API batch: progress, bulk actions, name field, notes, limits.

Also the run list's failure reason and latest export, and the sources of run findings.

Every document, reply and value is synthetic.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from app.config.bundle import ConfigBundle
from app.contracts.extraction import ExcludedItem, ExtractionOutput
from app.contracts.verification import ExcludedItemChallenge, VerificationOutput
from app.llm.fake_client import FakeReply
from app.validation import codes
from tests.fixtures.fake_llm import TABLE_CHUNK_ID, extraction_reply, missed_row
from tests.fixtures.make_documents import REAGENT_TABLE, WORD_FILE
from tests.integration.api_helpers import (
    TWO_ROWS,
    USER,
    ApiHarness,
    assert_error,
    happy_replies,
    make_settings,
    open_api,
    read_file,
)

RUN_ID = "run_0001"

# The synthetic table row the extraction leaves out, and that the agent challenges
EXCLUDED_ROW = 4

pytestmark = pytest.mark.usefixtures("blank_environment")


# ----- Helpers -----


def list_issues(view: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield every issue summary of a review view: run, record and cell issues."""
    yield from view["run_issues"]
    for row in view["rows"]:
        yield from row["record_issues"]
        for cell in row["cells"]:
            yield from cell["issues"]


def find_field_with_errors(api: ApiHarness) -> tuple[str, str]:
    """Return a list field with an open error in both records, and another value from its list.

    A new value changes the issue's key, so the old issue is resolved (CONTRACTS §4a).
    """
    fields = api.client.get(f"/runs/{RUN_ID}/fields").json()["fields"]
    view = api.client.get(f"/runs/{RUN_ID}/records").json()
    for field in fields:
        cells = [c for row in view["rows"] for c in row["cells"] if c["field"] == field["key"]]
        if not field["has_lookup_list"] or not all(has_open_error(cell) for cell in cells):
            continue
        current = {cell["value"] for cell in cells}
        other = [value for value in field["allowed_values"] if value not in current]
        if other:
            return field["key"], other[0]
    raise AssertionError("The synthetic run has no list field with an error to change.")


def has_open_error(cell: dict[str, Any]) -> bool:
    """Return True if a cell has an open error issue."""
    return any(i["severity"] == "error" and i["status"] == "open" for i in cell["issues"])


def set_value(
    change_id: str, record_id: str, field: str, value: str, bulk_id: str | None
) -> dict[str, Any]:
    """Return a set_value change, part of a bulk action when `bulk_id` is given."""
    change = {"type": "set_value", "change_id": change_id, "record_id": record_id}
    return {**change, "field": field, "value": value, "bulk_id": bulk_id}


def finding_replies(bundle: ConfigBundle) -> dict[str, list[FakeReply]]:
    """Return replies with an excluded table row the agent challenges and a missed row."""
    extraction = ExtractionOutput.model_validate_json(
        extraction_reply(bundle.field_rules, TWO_ROWS)
    )
    item = REAGENT_TABLE[EXCLUDED_ROW][0]
    extraction.excluded_items = [
        ExcludedItem(item=item, reason="synthetic: equipment", chunk_ids=[TABLE_CHUNK_ID])
    ]
    # The agent writes the item name in other case and spacing; it still finds its chunks
    challenge = ExcludedItemChallenge(item=f"  {item.upper()} ", reason="synthetic: a material")
    verification = VerificationOutput(
        field_findings=[],
        record_findings=[],
        missed_candidates=[missed_row(3)],
        excluded_item_challenges=[challenge],
        unreported_conflicts=[],
    )
    return {
        "extraction": [extraction.model_dump_json()],
        "extraction_verification": [verification.model_dump_json()],
    }


def start_happy_run(api: ApiHarness, documents: dict[str, Path]) -> None:
    """Start the two-record synthetic run and check it reached review."""
    response = api.start_run([read_file(documents, WORD_FILE)])
    assert response.status_code == 202, response.text
    assert api.client.get(f"/runs/{RUN_ID}").json()["status"] == "in_review"


# ----- Progress counts -----


def test_progress_counts_resolved_and_total_issues(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """Accepting a warning and fixing an error each count as resolved; grey issues never count."""
    with open_api(make_settings(tmp_path), happy_replies(bundle)) as api:
        start_happy_run(api, synthetic_documents)
        view = api.client.get(f"/runs/{RUN_ID}/records").json()
        counts = view["counts"]
        assert counts["resolved_issues"] == 0
        assert counts["total_issues"] == counts["open_errors"] + counts["open_warnings"]
        # Accept one warning that may be accepted on its own
        warning = next(
            issue
            for issue in list_issues(view)
            if issue["severity"] == "warning" and not issue["individual_review"]
        )
        accept = {
            "type": "accept_warning",
            "change_id": "chg_0001",
            "issue_id": warning["issue_id"],
        }
        api.post_changes(RUN_ID, [accept])
        accepted = api.client.post(f"/runs/{RUN_ID}/recheck").json()["counts"]
        assert accepted["resolved_issues"] == 1
        assert accepted["total_issues"] == counts["total_issues"]
        # Fix an error by setting a value: its issue is resolved
        field, value = find_field_with_errors(api)
        api.post_changes(RUN_ID, [set_value("chg_0002", "rec_0001", field, value, None)])
        fixed = api.client.post(f"/runs/{RUN_ID}/recheck").json()["counts"]
        assert fixed["resolved_issues"] >= 2
        assert fixed["total_issues"] >= fixed["resolved_issues"]
        assert api.client.get(f"/runs/{RUN_ID}/records").json()["counts"] == fixed


# ----- Bulk action list -----


def test_bulk_action_list_shows_a_bulk_action_and_its_undo(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """A bulk action is listed with its records; after undo it is undone and cannot be undone."""
    with open_api(make_settings(tmp_path), happy_replies(bundle)) as api:
        start_happy_run(api, synthetic_documents)
        assert api.client.get(f"/runs/{RUN_ID}/bulk-actions").json() == []
        field, value = find_field_with_errors(api)
        changes = [
            set_value("chg_0001", "rec_0001", field, value, "blk_0001"),
            set_value("chg_0002", "rec_0002", field, value, "blk_0001"),
        ]
        api.post_changes(RUN_ID, changes)
        pending = api.client.get(f"/runs/{RUN_ID}/bulk-actions").json()
        assert [action["is_pending"] for action in pending] == [True]
        api.client.post(f"/runs/{RUN_ID}/recheck")
        (action,) = api.client.get(f"/runs/{RUN_ID}/bulk-actions").json()
        assert action["bulk_id"] == "blk_0001"
        assert action["change_type"] == "set_value"
        assert action["field"] == field
        assert action["issue_code"] is None
        assert (action["record_count"], action["change_count"]) == (2, 2)
        assert action["created_by"] == USER
        assert action["is_pending"] is False
        assert (action["is_undone"], action["can_undo"]) == (False, True)
        # Undo it: listed as undone, by whom, and no longer undoable
        undo = {"type": "undo_bulk", "change_id": "chg_0003", "bulk_id": "blk_0001"}
        api.post_changes(RUN_ID, [undo])
        api.client.post(f"/runs/{RUN_ID}/recheck")
        (undone,) = api.client.get(f"/runs/{RUN_ID}/bulk-actions").json()
        assert (undone["is_undone"], undone["can_undo"]) == (True, False)
        assert undone["undone_by"] == USER
        assert undone["undone_at"] is not None
        assert_error(api.client.get("/runs/run_0099/bulk-actions"), 404, "RUN_NOT_FOUND")


# ----- Record name field and note_required -----


def test_exactly_one_field_is_the_record_name(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """`is_record_name` marks exactly the config's record name field."""
    with open_api(make_settings(tmp_path), happy_replies(bundle)) as api:
        start_happy_run(api, synthetic_documents)
        fields = api.client.get(f"/runs/{RUN_ID}/fields").json()["fields"]
        named = [field["key"] for field in fields if field["is_record_name"]]
        assert named == [bundle.field_rules.record_name_field().key]


def test_note_required_and_run_finding_sources(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """Run findings cite their chunks; note_required follows the catalogue on every issue."""
    settings = make_settings(tmp_path, max_reextract=0)
    with open_api(settings, finding_replies(bundle)) as api:
        start_happy_run(api, synthetic_documents)
        view = api.client.get(f"/runs/{RUN_ID}/records").json()
        catalogue = bundle.issue_catalogue
        for issue in list_issues(view):
            definitions = catalogue.run_issues | catalogue.record_issues
            assert issue["note_required"] == definitions[issue["code"]].note_required
        by_code = {issue["code"]: issue for issue in view["run_issues"]}
        for code in (codes.MISSED_CANDIDATES_UNRESOLVED, codes.EXCLUDED_ITEM_CHALLENGED):
            sources = by_code[code]["sources"]
            assert [source["chunk_id"] for source in sources] == [TABLE_CHUNK_ID]
            assert sources[0]["file_name"] == WORD_FILE
        record = api.client.get(f"/runs/{RUN_ID}/records/rec_0001").json()
        for issue in record["issues"]:
            definitions = catalogue.record_issues
            assert issue["note_required"] == definitions[issue["code"]].note_required


def test_individual_review_run_issue_is_accepted_after_its_source_is_viewed(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """A run finding needs the source viewed and a note; then it is accepted."""
    settings = make_settings(tmp_path, max_reextract=0)
    with open_api(settings, finding_replies(bundle)) as api:
        start_happy_run(api, synthetic_documents)
        view = api.client.get(f"/runs/{RUN_ID}/records").json()
        issue = next(
            i for i in view["run_issues"] if i["code"] == codes.MISSED_CANDIDATES_UNRESOLVED
        )
        assert issue["individual_review"] is True
        assert issue["note_required"] is True
        accept = {"type": "accept_warning", "change_id": "chg_0001", "issue_id": issue["issue_id"]}
        assert_error(api.post_changes(RUN_ID, [accept]), 400, "CHANGE_INVALID")
        viewed = {**accept, "source_viewed": True}
        assert_error(api.post_changes(RUN_ID, [viewed]), 400, "CHANGE_INVALID")
        noted = {**viewed, "note": "synthetic: added outside the tool"}
        assert api.post_changes(RUN_ID, [noted]).status_code == 200
        api.client.post(f"/runs/{RUN_ID}/recheck")
        after = api.client.get(f"/runs/{RUN_ID}/records").json()
        rechecked = next(i for i in after["run_issues"] if i["issue_id"] == issue["issue_id"])
        assert rechecked["status"] == "accepted"
        # The re-check raised the finding again from the stored findings, sources kept
        assert rechecked["sources"] == issue["sources"]


# ----- Upload limits -----


def test_upload_limits_are_null_when_blank(tmp_path: Path) -> None:
    """Blank limits are null (no limit)."""
    with open_api(make_settings(tmp_path)) as api:
        response = api.client.get("/settings/upload-limits")
        assert response.status_code == 200, response.text
        assert response.json() == {"max_file_size_mb": None, "max_files_per_run": None}


def test_upload_limits_are_numbers_when_set(tmp_path: Path) -> None:
    """Set limits are returned as numbers, and nothing else is exposed."""
    settings = make_settings(tmp_path, max_file_size_mb=25, max_files_per_run=10)
    with open_api(settings) as api:
        limits = api.client.get("/settings/upload-limits").json()
        assert limits == {"max_file_size_mb": 25, "max_files_per_run": 10}


# ----- Run list: failure reason and latest export -----


def test_run_list_gives_failure_reason_and_latest_export(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """A failed run names why; a run in review shows its newest export."""
    with open_api(make_settings(tmp_path), happy_replies(bundle)) as api:
        start_happy_run(api, synthetic_documents)
        # A file ingest cannot read fails the second run
        api.start_run([("synthetic_broken.pdf", b"synthetic: not a PDF")])
        summaries = {s["run_id"]: s for s in api.client.get("/runs").json()}
        failed = summaries["run_0002"]
        assert failed["status"] == "failed"
        run_issues = api.client.get("/runs/run_0002").json()["run_issues"]
        first_error = next(issue for issue in run_issues if issue["severity"] == "error")
        assert failed["failure_reason"] == first_error["message"]
        assert summaries[RUN_ID]["failure_reason"] is None
        assert summaries[RUN_ID]["latest_export"] is None
        # Two draft exports: the list shows the second
        api.client.post(f"/runs/{RUN_ID}/exports")
        api.client.post(f"/runs/{RUN_ID}/exports")
        summary = next(s for s in api.client.get("/runs").json() if s["run_id"] == RUN_ID)
        latest = summary["latest_export"]
        assert (latest["number"], latest["is_draft"]) == (2, True)
        assert latest["exported_at"]
