"""Review database tests: schema version, runs, records, changes, judge cache, admin versions."""

import sqlite3
from pathlib import Path

import pytest

from app.config.bundle import ConfigBundle
from app.contracts.export import ExportInfo
from app.contracts.judge import JudgeOutput, Judgment
from app.contracts.run import AuditEvent, RunInfo
from app.settings import MissingSettingError, Settings
from app.storage.review_db import (
    DatabaseJudgeCache,
    DataVersion,
    ReviewDatabase,
    ReviewDatabaseError,
    RunNotFoundError,
    open_review_db,
)
from tests.unit.review_helpers import NOW, RUN_ID, USER
from tests.unit.validation_helpers import make_record


@pytest.fixture
def database(tmp_path: Path) -> ReviewDatabase:
    """Return a new review database in a temp folder."""
    return ReviewDatabase(tmp_path / "data" / "review.sqlite")


def make_run(bundle: ConfigBundle, run_id: str = RUN_ID) -> RunInfo:
    """Return a synthetic run in review."""
    return RunInfo(
        run_id=run_id,
        name="synthetic run",
        created_by=USER,
        created_at=NOW,
        config_versions=bundle.versions(),
        reference_data_version="ref-synthetic-1",
        status="in_review",
    )


def test_run_round_trips(database: ReviewDatabase, bundle: ConfigBundle) -> None:
    """A stored run reads back equal, and its columns can be updated."""
    run = make_run(bundle)
    database.add_run(run)
    assert database.read_run(RUN_ID) == run
    database.update_run(RUN_ID, name="synthetic renamed")
    database.set_verified(RUN_ID, USER, NOW)
    stored = database.read_run(RUN_ID)
    assert (stored.name, stored.is_verified, stored.verified_at) == ("synthetic renamed", True, NOW)
    assert database.list_runs() == [stored]


def test_unknown_or_repeated_run_is_refused(database: ReviewDatabase, bundle: ConfigBundle) -> None:
    """Reading an unknown run and adding a run ID twice give plain errors."""
    with pytest.raises(RunNotFoundError):
        database.read_run("run_9999")
    database.add_run(make_run(bundle))
    with pytest.raises(ReviewDatabaseError):
        database.add_run(make_run(bundle))


def test_records_keep_their_order(database: ReviewDatabase, bundle: ConfigBundle) -> None:
    """Records read back in the order written."""
    database.add_run(make_run(bundle))
    records = [make_record(bundle, f"rec_000{n}", f"Syn {n}") for n in (3, 1, 2)]
    database.write_records(RUN_ID, records)
    assert database.read_records(RUN_ID) == records


def test_schema_version_is_stored_and_checked(tmp_path: Path) -> None:
    """A database written with another schema version is refused, not changed."""
    path = tmp_path / "review.sqlite"
    ReviewDatabase(path).close()
    connection = sqlite3.connect(path)
    connection.execute("UPDATE schema_info SET value = '999' WHERE key = 'schema_version'")
    connection.commit()
    connection.close()
    with pytest.raises(ReviewDatabaseError, match="schema version 999"):
        ReviewDatabase(path)


def test_failed_transaction_writes_nothing(database: ReviewDatabase, bundle: ConfigBundle) -> None:
    """An error inside a transaction rolls back every write in it."""
    with pytest.raises(RuntimeError), database.transaction():
        database.add_run(make_run(bundle))
        raise RuntimeError("synthetic failure")
    assert database.list_runs() == []


def test_blank_review_db_setting_is_named(tmp_path: Path) -> None:
    """Opening the database with REVIEW_DB blank names the setting."""
    with pytest.raises(MissingSettingError, match="REVIEW_DB"):
        open_review_db(Settings(review_db=None))
    database = open_review_db(Settings(review_db=str(tmp_path / "review.sqlite")))
    assert database.list_runs() == []


def test_judge_cache_survives_a_new_connection(tmp_path: Path) -> None:
    """Judge results stored through the database cache are found by a later connection."""
    path = tmp_path / "review.sqlite"
    output = JudgeOutput(
        judgments=[Judgment(candidate_id="ref_0001", verdict="same", reason="synthetic")]
    )
    DatabaseJudgeCache(ReviewDatabase(path)).put("key-1", output)
    cache = DatabaseJudgeCache(ReviewDatabase(path))
    assert (cache.get("key-1"), cache.get("key-2")) == (output, None)


def test_exports_and_audit_events_round_trip(
    database: ReviewDatabase, bundle: ConfigBundle
) -> None:
    """Exports list by number; audit events by run, oldest first."""
    database.add_run(make_run(bundle))
    exports = [
        ExportInfo(
            export_id=f"exp_000{n}",
            number=n,
            is_draft=True,
            loader_file=f"synthetic {n}.xlsx",
            audit_file=f"synthetic {n} audit.xlsx",
            exported_at=NOW,
            exported_by=USER,
        )
        for n in (2, 1)
    ]
    for export in exports:
        database.add_export(RUN_ID, export)
    assert [e.number for e in database.list_exports(RUN_ID)] == [1, 2]
    events = [AuditEvent(event=name, run_id=RUN_ID, by=USER, at=NOW) for name in ("a", "b")]
    database.add_audit_events(events)
    assert database.read_audit_events(RUN_ID) == events


def make_version(upload_id: str) -> DataVersion:
    """Return a pending synthetic upload."""
    return DataVersion(
        upload_id=upload_id,
        file_ref=f"lookup_lists/{upload_id}.xlsx",
        uploaded_by=USER,
        uploaded_at=NOW,
    )


def test_one_data_version_is_current(database: ReviewDatabase) -> None:
    """Applying an upload makes it current and the earlier current one superseded; restore works."""
    assert database.read_current_data_version("lookup") is None
    for upload_id in ("upl_0001", "upl_0002"):
        database.add_data_version("lookup", make_version(upload_id))
    database.make_data_version_current("lookup", "upl_0001", "v1", USER, NOW)
    database.make_data_version_current("lookup", "upl_0002", "v2", USER, NOW)
    statuses = [(v.version_id, v.status) for v in database.list_data_versions("lookup")]
    assert statuses == [("v1", "superseded"), ("v2", "current")]
    # Restoring keeps the version's own ID
    restored = database.make_data_version_current("lookup", "upl_0001", "v3", USER, NOW)
    assert (restored.version_id, restored.status) == ("v1", "current")
    assert database.list_data_versions("reference") == []


def test_admin_events_are_kept(database: ReviewDatabase) -> None:
    """Admin actions are stored without a run."""
    event = AuditEvent(event="lookup_version_applied", run_id=None, by=USER, at=NOW)
    database.add_admin_event(event)
    assert database.read_admin_events() == [event]
