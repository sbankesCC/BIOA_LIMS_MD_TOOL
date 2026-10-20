"""Review database (CONTRACTS §7): the only changing copy of a run once processing ends.

Plain sqlite3 with a schema version. Holds runs, records, issues (with history), changes, exports
and audit events per run, plus the duplicate judge cache, admin data versions and admin events.
"""

import json
import sqlite3
import threading
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter

from app.contracts.changes import ChangeStatus, StoredChange
from app.contracts.export import ExportInfo
from app.contracts.extraction import ExcludedItem
from app.contracts.issue import Issue, IssueHistoryEntry
from app.contracts.judge import JudgeOutput
from app.contracts.record import StoredRecord
from app.contracts.run import AuditEvent, RunInfo, RunStatus
from app.settings import Settings
from app.validation.service import ProcessingFindings

# Bump when a table changes; an existing file with another version is refused, never rewritten
SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_info (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    config_versions TEXT NOT NULL,
    reference_data_version TEXT,
    models TEXT NOT NULL DEFAULT '{}',
    retry_of TEXT,
    status TEXT NOT NULL,
    is_verified INTEGER NOT NULL DEFAULT 0,
    verified_by TEXT,
    verified_at TEXT,
    findings TEXT NOT NULL DEFAULT '{}',
    excluded_items TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS records (
    run_id TEXT NOT NULL REFERENCES runs (run_id),
    record_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (run_id, record_id)
);
CREATE TABLE IF NOT EXISTS issues (
    run_id TEXT NOT NULL REFERENCES runs (run_id),
    issue_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (run_id, issue_id)
);
CREATE TABLE IF NOT EXISTS issue_history (
    entry_number INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs (run_id),
    issue_id TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS changes (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs (run_id),
    change_id TEXT NOT NULL,
    type TEXT NOT NULL,
    bulk_id TEXT,
    status TEXT NOT NULL,
    data TEXT NOT NULL,
    applied_at TEXT,
    old_value TEXT,
    new_value TEXT,
    before_state TEXT,
    after_state TEXT,
    undone_by TEXT,
    UNIQUE (run_id, change_id)
);
CREATE TABLE IF NOT EXISTS exports (
    run_id TEXT NOT NULL REFERENCES runs (run_id),
    export_id TEXT NOT NULL,
    number INTEGER NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (run_id, export_id)
);
CREATE TABLE IF NOT EXISTS audit_events (
    entry_number INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS duplicate_judgments (
    cache_key TEXT PRIMARY KEY,
    output TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lookup_versions (
    upload_id TEXT PRIMARY KEY,
    version_id TEXT UNIQUE,
    status TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reference_versions (
    upload_id TEXT PRIMARY KEY,
    version_id TEXT UNIQUE,
    status TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS admin_events (
    entry_number INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL
);
"""

# Run columns written from RunInfo, in table order (config versions and models as JSON)
RUN_COLUMNS = (
    "run_id",
    "name",
    "created_by",
    "created_at",
    "config_versions",
    "reference_data_version",
    "models",
    "retry_of",
    "status",
    "is_verified",
    "verified_by",
    "verified_at",
)

# Admin data versions: lookup list workbooks and reference data snapshots, one table each
DataVersionKind = Literal["lookup", "reference"]
DATA_VERSION_TABLES: dict[DataVersionKind, str] = {
    "lookup": "lookup_versions",
    "reference": "reference_versions",
}
DataVersionStatus = Literal["pending", "current", "superseded"]

ISSUE_HISTORY_LIST = TypeAdapter(list[IssueHistoryEntry])
EXCLUDED_ITEM_LIST = TypeAdapter(list[ExcludedItem])


class ReviewDatabaseError(Exception):
    """Raised when the review database cannot do what was asked; the message says what to do."""


class RunNotFoundError(ReviewDatabaseError):
    """Raised when a run ID is not in the review database."""

    def __init__(self, run_id: str) -> None:
        """Build a plain message naming the run."""
        self.run_id = run_id
        super().__init__(f"Run {run_id} was not found. Check the run ID.")


class StoredChangeRow(BaseModel):
    """A change row: the stored change plus what applying it did (for undo and the Edits sheet).

    `before_state` and `after_state` hold the part of the run the change touched, as JSON.
    """

    model_config = ConfigDict(extra="forbid")

    sequence: int
    stored: StoredChange
    applied_at: datetime | None = None
    old_value: str | None = None
    new_value: str | None = None
    before_state: JsonValue = None
    after_state: JsonValue = None
    undone_by: str | None = None


class AppliedChange(BaseModel):
    """What applying one change did: values for the Edits sheet and states for undo."""

    change_id: str
    applied_at: datetime
    old_value: str | None = None
    new_value: str | None = None
    before_state: JsonValue = None
    after_state: JsonValue = None


class DataVersion(BaseModel):
    """One admin upload of lookup lists or reference data, and whether it is current.

    `upload_id` names the upload; `version_id` (e.g. `v1`) is given when it is first applied.
    `file_ref` is relative to STORAGE_DIR. `summary` holds the check report or diff counts.
    """

    model_config = ConfigDict(extra="forbid")

    upload_id: str
    version_id: str | None = None
    status: DataVersionStatus = "pending"
    file_ref: str
    based_on_version: str | None = None
    uploaded_by: str
    uploaded_at: datetime
    applied_by: str | None = None
    applied_at: datetime | None = None
    summary: dict[str, JsonValue] = {}


def open_review_db(settings: Settings) -> "ReviewDatabase":
    """Open the review database at REVIEW_DB; raise MissingSettingError if it is blank."""
    return ReviewDatabase(settings.require_path("REVIEW_DB"))


class ReviewDatabase:
    """The review database: one SQLite connection, shared by threads under a lock."""

    def __init__(self, path: Path) -> None:
        """Open (or create) the database file and check its schema version."""
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = threading.RLock()
        self.depth = 0
        # Autocommit mode: `transaction()` opens and closes every transaction itself
        self.connection = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.create_schema()

    def close(self) -> None:
        """Close the connection."""
        self.connection.close()

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection]:
        """Run the block as one transaction; nested blocks join the outer one."""
        with self.lock:
            is_outer = self.depth == 0
            if is_outer:
                self.connection.execute("BEGIN IMMEDIATE")
            self.depth += 1
            try:
                yield self.connection
            except BaseException:
                self.depth -= 1
                if is_outer:
                    self.connection.execute("ROLLBACK")
                raise
            self.depth -= 1
            if is_outer:
                self.connection.execute("COMMIT")

    def create_schema(self) -> None:
        """Create missing tables and refuse a file written with another schema version."""
        with self.lock:
            self.connection.executescript(SCHEMA)
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT value FROM schema_info WHERE key = 'schema_version'"
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO schema_info (key, value) VALUES ('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
            elif row["value"] != str(SCHEMA_VERSION):
                raise ReviewDatabaseError(
                    f"The review database {self.path} has schema version {row['value']}, but "
                    f"this app needs version {SCHEMA_VERSION}. Move the file aside or set "
                    "REVIEW_DB to a new file, then restart the app."
                )

    def read_all(self, sql: str, parameters: Sequence[object] = ()) -> list[sqlite3.Row]:
        """Run a query under the lock and return every row."""
        with self.lock:
            return self.connection.execute(sql, parameters).fetchall()

    # ----- Runs -----

    def add_run(self, run: RunInfo) -> None:
        """Add a new run; refuse a run ID that already exists."""
        values = run_to_row(run)
        placeholders = ", ".join("?" for _ in RUN_COLUMNS)
        with self.transaction() as connection:
            try:
                connection.execute(
                    f"INSERT INTO runs ({', '.join(RUN_COLUMNS)}) VALUES ({placeholders})",
                    values,
                )
            except sqlite3.IntegrityError as error:
                raise ReviewDatabaseError(
                    f"Run {run.run_id} already exists. Start the run with a new ID."
                ) from error

    def read_run(self, run_id: str) -> RunInfo:
        """Return one run; raise RunNotFoundError if it is not stored."""
        rows = self.read_all("SELECT * FROM runs WHERE run_id = ?", (run_id,))
        if not rows:
            raise RunNotFoundError(run_id)
        return row_to_run(rows[0])

    def list_runs(self) -> list[RunInfo]:
        """Return every run, newest first."""
        rows = self.read_all("SELECT * FROM runs ORDER BY created_at DESC, run_id DESC")
        return [row_to_run(row) for row in rows]

    def update_run(self, run_id: str, **values: object) -> None:
        """Set some run columns (e.g. `status`, `name`); raise RunNotFoundError if not stored."""
        unknown = [name for name in values if name not in RUN_COLUMNS or name == "run_id"]
        if unknown:
            raise ValueError(f"Unknown run columns {unknown}. Use names from RUN_COLUMNS.")
        assignments = ", ".join(f"{name} = ?" for name in values)
        parameters = [to_column_value(value) for value in values.values()]
        with self.transaction() as connection:
            cursor = connection.execute(
                f"UPDATE runs SET {assignments} WHERE run_id = ?", (*parameters, run_id)
            )
            if cursor.rowcount == 0:
                raise RunNotFoundError(run_id)

    def set_run_status(self, run_id: str, status: RunStatus) -> None:
        """Set a run's status."""
        self.update_run(run_id, status=status)

    def set_verified(self, run_id: str, by: str, at: datetime) -> None:
        """Put the verified label on a run (who, when)."""
        self.update_run(run_id, is_verified=True, verified_by=by, verified_at=at)

    def clear_verified(self, run_id: str) -> None:
        """Remove the verified label from a run."""
        self.update_run(run_id, is_verified=False, verified_by=None, verified_at=None)

    def save_processing_result(
        self,
        run_id: str,
        records: Sequence[StoredRecord],
        issues: Sequence[Issue],
        findings: ProcessingFindings,
        excluded_items: Sequence[ExcludedItem],
        at: datetime,
    ) -> None:
        """Store what processing produced (end of the graph) and open each issue's history."""
        with self.transaction() as connection:
            # Excluded items have their own column, so the findings JSON leaves them out
            connection.execute(
                "UPDATE runs SET findings = ?, excluded_items = ? WHERE run_id = ?",
                (
                    findings.model_dump_json(exclude={"excluded_items"}),
                    EXCLUDED_ITEM_LIST.dump_json(list(excluded_items)).decode("utf-8"),
                    run_id,
                ),
            )
            self.write_records(run_id, records)
            self.write_issues(run_id, issues)
            opened = [
                IssueHistoryEntry(issue_id=issue.issue_id, action="opened", by=None, at=at)
                for issue in issues
            ]
            self.add_issue_history(run_id, opened)

    def read_findings(self, run_id: str) -> ProcessingFindings:
        """Return the processing findings stored for a run (re-checks raise them again).

        The excluded items come from their own column.
        """
        rows = self.read_all("SELECT findings FROM runs WHERE run_id = ?", (run_id,))
        if not rows:
            raise RunNotFoundError(run_id)
        findings = ProcessingFindings.model_validate_json(rows[0]["findings"])
        return findings.model_copy(update={"excluded_items": self.read_excluded_items(run_id)})

    def read_excluded_items(self, run_id: str) -> list[ExcludedItem]:
        """Return the items extraction left out of a run."""
        rows = self.read_all("SELECT excluded_items FROM runs WHERE run_id = ?", (run_id,))
        if not rows:
            raise RunNotFoundError(run_id)
        return EXCLUDED_ITEM_LIST.validate_json(rows[0]["excluded_items"])

    # ----- Records and issues -----

    def write_records(self, run_id: str, records: Sequence[StoredRecord]) -> None:
        """Replace a run's records, keeping their order."""
        with self.transaction() as connection:
            connection.execute("DELETE FROM records WHERE run_id = ?", (run_id,))
            connection.executemany(
                "INSERT INTO records (run_id, record_id, position, data) VALUES (?, ?, ?, ?)",
                [
                    (run_id, record.record_id, position, record.model_dump_json())
                    for position, record in enumerate(records)
                ],
            )

    def read_records(self, run_id: str) -> list[StoredRecord]:
        """Return a run's records in their order."""
        rows = self.read_all(
            "SELECT data FROM records WHERE run_id = ? ORDER BY position", (run_id,)
        )
        return [StoredRecord.model_validate_json(row["data"]) for row in rows]

    def write_issues(self, run_id: str, issues: Sequence[Issue]) -> None:
        """Replace a run's issues (open, accepted and resolved), keeping their order."""
        with self.transaction() as connection:
            connection.execute("DELETE FROM issues WHERE run_id = ?", (run_id,))
            connection.executemany(
                "INSERT INTO issues (run_id, issue_id, position, data) VALUES (?, ?, ?, ?)",
                [
                    (run_id, issue.issue_id, position, issue.model_dump_json())
                    for position, issue in enumerate(issues)
                ],
            )

    def read_issues(self, run_id: str) -> list[Issue]:
        """Return a run's issues in their order."""
        rows = self.read_all(
            "SELECT data FROM issues WHERE run_id = ? ORDER BY position", (run_id,)
        )
        return [Issue.model_validate_json(row["data"]) for row in rows]

    def add_issue_history(self, run_id: str, entries: Sequence[IssueHistoryEntry]) -> None:
        """Append steps to the issues' history."""
        with self.transaction() as connection:
            connection.executemany(
                "INSERT INTO issue_history (run_id, issue_id, data) VALUES (?, ?, ?)",
                [(run_id, entry.issue_id, entry.model_dump_json()) for entry in entries],
            )

    def read_issue_history(self, run_id: str) -> list[IssueHistoryEntry]:
        """Return every issue history step of a run, oldest first."""
        rows = self.read_all(
            "SELECT data FROM issue_history WHERE run_id = ? ORDER BY entry_number", (run_id,)
        )
        return [IssueHistoryEntry.model_validate_json(row["data"]) for row in rows]

    # ----- Changes -----

    def add_changes(self, run_id: str, changes: Sequence[StoredChange]) -> None:
        """Store changes as pending, in the order given."""
        with self.transaction() as connection:
            connection.executemany(
                "INSERT INTO changes (run_id, change_id, type, bulk_id, status, data) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        run_id,
                        stored.change.change_id,
                        stored.change.type,
                        read_bulk_id(stored),
                        stored.status,
                        stored.model_dump_json(),
                    )
                    for stored in changes
                ],
            )

    def read_changes(
        self, run_id: str, status: ChangeStatus | None = None
    ) -> list[StoredChangeRow]:
        """Return a run's changes in the order they were saved, optionally of one status."""
        sql = "SELECT * FROM changes WHERE run_id = ?"
        parameters: list[object] = [run_id]
        if status is not None:
            sql += " AND status = ?"
            parameters.append(status)
        rows = self.read_all(sql + " ORDER BY sequence", parameters)
        return [row_to_change(row) for row in rows]

    def read_change_ids(self, run_id: str) -> set[str]:
        """Return the IDs of every change stored for a run (to ignore resent changes)."""
        rows = self.read_all("SELECT change_id FROM changes WHERE run_id = ?", (run_id,))
        return {row["change_id"] for row in rows}

    def mark_change_applied(self, run_id: str, applied: AppliedChange) -> None:
        """Mark a pending change applied, with its old and new values and states."""
        with self.transaction() as connection:
            connection.execute(
                "UPDATE changes SET status = 'applied', applied_at = ?, old_value = ?, "
                "new_value = ?, before_state = ?, after_state = ? "
                "WHERE run_id = ? AND change_id = ?",
                (
                    applied.applied_at.isoformat(),
                    applied.old_value,
                    applied.new_value,
                    json.dumps(applied.before_state),
                    json.dumps(applied.after_state),
                    run_id,
                    applied.change_id,
                ),
            )
            self.rewrite_change_status(run_id, applied.change_id)

    def rewrite_change_status(self, run_id: str, change_id: str) -> None:
        """Keep the status inside the stored change JSON equal to the status column."""
        rows = self.read_all(
            "SELECT data, status FROM changes WHERE run_id = ? AND change_id = ?",
            (run_id, change_id),
        )
        stored = StoredChange.model_validate_json(rows[0]["data"])
        updated = stored.model_copy(update={"status": rows[0]["status"]})
        with self.transaction() as connection:
            connection.execute(
                "UPDATE changes SET data = ? WHERE run_id = ? AND change_id = ?",
                (updated.model_dump_json(), run_id, change_id),
            )

    def mark_change_undone(self, run_id: str, change_id: str, undone_by: str) -> None:
        """Record that an applied change was undone, and by which undo change."""
        with self.transaction() as connection:
            connection.execute(
                "UPDATE changes SET undone_by = ? WHERE run_id = ? AND change_id = ?",
                (undone_by, run_id, change_id),
            )

    # ----- Exports and audit events -----

    def add_export(self, run_id: str, export: ExportInfo) -> None:
        """Store one export of a run."""
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO exports (run_id, export_id, number, data) VALUES (?, ?, ?, ?)",
                (run_id, export.export_id, export.number, export.model_dump_json()),
            )

    def list_exports(self, run_id: str) -> list[ExportInfo]:
        """Return a run's exports by number."""
        rows = self.read_all("SELECT data FROM exports WHERE run_id = ? ORDER BY number", (run_id,))
        return [ExportInfo.model_validate_json(row["data"]) for row in rows]

    def add_audit_events(self, events: Sequence[AuditEvent]) -> None:
        """Append business events to the audit trail."""
        with self.transaction() as connection:
            connection.executemany(
                "INSERT INTO audit_events (run_id, data) VALUES (?, ?)",
                [(event.run_id, event.model_dump_json()) for event in events],
            )

    def read_audit_events(self, run_id: str) -> list[AuditEvent]:
        """Return a run's audit events, oldest first."""
        rows = self.read_all(
            "SELECT data FROM audit_events WHERE run_id = ? ORDER BY entry_number", (run_id,)
        )
        return [AuditEvent.model_validate_json(row["data"]) for row in rows]

    # ----- Duplicate judge cache -----

    def read_judgment(self, cache_key: str) -> JudgeOutput | None:
        """Return the cached judge result for a key, or None."""
        rows = self.read_all(
            "SELECT output FROM duplicate_judgments WHERE cache_key = ?", (cache_key,)
        )
        return JudgeOutput.model_validate_json(rows[0]["output"]) if rows else None

    def write_judgment(self, cache_key: str, output: JudgeOutput) -> None:
        """Store a judge result under its key (a repeated key keeps the newest result)."""
        with self.transaction() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO duplicate_judgments (cache_key, output) VALUES (?, ?)",
                (cache_key, output.model_dump_json()),
            )

    # ----- Admin data versions and admin events -----

    def add_data_version(self, kind: DataVersionKind, version: DataVersion) -> None:
        """Store a new admin upload (usually pending) of lookup lists or reference data."""
        with self.transaction() as connection:
            connection.execute(
                f"INSERT INTO {DATA_VERSION_TABLES[kind]} (upload_id, version_id, status, data) "
                "VALUES (?, ?, ?, ?)",
                (version.upload_id, version.version_id, version.status, version.model_dump_json()),
            )

    def list_data_versions(self, kind: DataVersionKind) -> list[DataVersion]:
        """Return every upload of one kind, in upload order."""
        rows = self.read_all(f"SELECT data FROM {DATA_VERSION_TABLES[kind]} ORDER BY rowid")
        return [DataVersion.model_validate_json(row["data"]) for row in rows]

    def read_data_version(self, kind: DataVersionKind, upload_id: str) -> DataVersion:
        """Return one upload; raise ReviewDatabaseError if it is not stored."""
        versions = [v for v in self.list_data_versions(kind) if v.upload_id == upload_id]
        if not versions:
            raise ReviewDatabaseError(f"Upload {upload_id} was not found. Check the version list.")
        return versions[0]

    def read_current_data_version(self, kind: DataVersionKind) -> DataVersion | None:
        """Return the current version of one kind, or None (no admin version applied yet)."""
        current = [v for v in self.list_data_versions(kind) if v.status == "current"]
        return current[0] if current else None

    def make_data_version_current(
        self, kind: DataVersionKind, upload_id: str, version_id: str, by: str, at: datetime
    ) -> DataVersion:
        """Make one upload the current version (apply or restore); the old current is superseded."""
        version = self.read_data_version(kind, upload_id)
        applied = version.model_copy(
            update={
                "version_id": version.version_id or version_id,
                "status": "current",
                "applied_by": by,
                "applied_at": at,
            }
        )
        with self.transaction():
            previous = self.read_current_data_version(kind)
            if previous is not None and previous.upload_id != upload_id:
                self.write_data_version(kind, previous.model_copy(update={"status": "superseded"}))
            self.write_data_version(kind, applied)
        return applied

    def write_data_version(self, kind: DataVersionKind, version: DataVersion) -> None:
        """Overwrite one stored upload."""
        with self.transaction() as connection:
            connection.execute(
                f"UPDATE {DATA_VERSION_TABLES[kind]} SET version_id = ?, status = ?, data = ? "
                "WHERE upload_id = ?",
                (version.version_id, version.status, version.model_dump_json(), version.upload_id),
            )

    def add_admin_event(self, event: AuditEvent) -> None:
        """Append an admin action (upload, apply, restore) to the admin log."""
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO admin_events (data) VALUES (?)", (event.model_dump_json(),)
            )

    def read_admin_events(self) -> list[AuditEvent]:
        """Return every admin event, oldest first."""
        rows = self.read_all("SELECT data FROM admin_events ORDER BY entry_number")
        return [AuditEvent.model_validate_json(row["data"]) for row in rows]


class DatabaseJudgeCache:
    """The M5 `JudgeCache`, backed by the `duplicate_judgments` table (survives restarts)."""

    def __init__(self, database: ReviewDatabase) -> None:
        """Use the given review database."""
        self.database = database

    def get(self, key: str) -> JudgeOutput | None:
        """Return the cached result for a key, or None."""
        return self.database.read_judgment(key)

    def put(self, key: str, output: JudgeOutput) -> None:
        """Store a result under a key."""
        self.database.write_judgment(key, output)


def to_column_value(value: object) -> object:
    """Turn a Python value into what SQLite stores: datetimes as ISO text, models as JSON."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, BaseModel):
        return value.model_dump_json()
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return int(value)
    return value


def run_to_row(run: RunInfo) -> list[object]:
    """Return a run's column values in RUN_COLUMNS order."""
    return [to_column_value(getattr(run, column)) for column in RUN_COLUMNS]


def row_to_run(row: sqlite3.Row) -> RunInfo:
    """Build a RunInfo from a runs row."""
    values = {column: row[column] for column in RUN_COLUMNS}
    values["config_versions"] = json.loads(row["config_versions"])
    values["models"] = json.loads(row["models"])
    values["is_verified"] = bool(row["is_verified"])
    return RunInfo.model_validate(values)


def read_bulk_id(stored: StoredChange) -> str | None:
    """Return the bulk ID of a change that can be part of a bulk action (undo cannot)."""
    change = stored.change
    return None if change.type == "undo_bulk" else change.bulk_id


def row_to_change(row: sqlite3.Row) -> StoredChangeRow:
    """Build a StoredChangeRow from a changes row."""
    applied_at = row["applied_at"]
    return StoredChangeRow(
        sequence=row["sequence"],
        stored=StoredChange.model_validate_json(row["data"]),
        applied_at=datetime.fromisoformat(applied_at) if applied_at else None,
        old_value=row["old_value"],
        new_value=row["new_value"],
        before_state=json.loads(row["before_state"]) if row["before_state"] else None,
        after_state=json.loads(row["after_state"]) if row["after_state"] else None,
        undone_by=row["undone_by"],
    )
