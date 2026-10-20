"""Export service (ARCHITECTURE §4.10): re-checks if needed, then writes the loader and audit file.

Export is allowed at any time during review; an unverified run gives a draft. Files go to the
run's `exports/` folder with numbered names; the export is recorded in the review database.
"""

import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel

from app.config.dfd_template import DfdTemplate
from app.contracts.export import ExportInfo
from app.contracts.run import AuditEvent, RunInfo
from app.export.audit_rows import AuditSource, build_audit_rows
from app.export.audit_workbook import write_audit_workbook
from app.export.loader import write_loader
from app.ids import format_numbered_id
from app.logging_setup import log_event
from app.review.service import ReviewContext, recheck_run, require_in_review
from app.storage.review_db import ReviewDatabase
from app.storage.run_store import RunFolder
from app.validation.duplicates import find_name_rule

EXPORT_PREFIX = "exp_"
EXPORT_CREATED = "export_created"

# File names: "[run name] – export [n].xlsx" and "... – audit.xlsx"; drafts add "– draft"
NAME_SEPARATOR = " – "
EXPORT_WORD = "export"
AUDIT_WORD = "audit"
DRAFT_WORD = "draft"
FILE_EXTENSION = ".xlsx"

# Characters Windows does not allow in file names (and control characters) become "_"
UNSAFE_FILE_CHARACTERS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
SAFE_REPLACEMENT = "_"


@dataclass(frozen=True)
class ExportContext:
    """What an export needs besides the run: its review context, the template, and the models.

    `models` names the LLM model used per node (e.g. extraction), for the audit Summary.
    """

    review: ReviewContext
    template: DfdTemplate
    models: Mapping[str, str]


class ExportFileNames(BaseModel):
    """The loader and audit file names of one export."""

    loader: str
    audit: str


def make_export_file_names(run_name: str, number: int, is_draft: bool) -> ExportFileNames:
    """Return the numbered file names, with en dashes, and "– draft" for a draft export."""
    safe_name = UNSAFE_FILE_CHARACTERS.sub(SAFE_REPLACEMENT, run_name).strip() or SAFE_REPLACEMENT
    stem = f"{safe_name}{NAME_SEPARATOR}{EXPORT_WORD} {number}"
    draft = f"{NAME_SEPARATOR}{DRAFT_WORD}" if is_draft else ""
    return ExportFileNames(
        loader=f"{stem}{draft}{FILE_EXTENSION}",
        audit=f"{stem}{NAME_SEPARATOR}{AUDIT_WORD}{draft}{FILE_EXTENSION}",
    )


def export_run(
    database: ReviewDatabase,
    context: ExportContext,
    run_folder: RunFolder,
    run_id: str,
    user: str,
    at: datetime,
) -> ExportInfo:
    """Re-check if changes are pending, write both files, and record the export."""
    started = time.monotonic()
    with database.transaction():
        require_in_review(database, run_id)
        if database.read_changes(run_id, "pending"):
            recheck_run(database, context.review, run_id, user, at)
        run = database.read_run(run_id)
        export = make_export_info(database, run, run_folder, user, at)
        row_count = write_export_files(database, context, run_folder, run, export)
        database.add_export(run_id, export)
        database.add_audit_events([make_export_event(export, run_id)])
    log_event(
        "export_created",
        run_id=run_id,
        duration_ms=int((time.monotonic() - started) * 1000),
        details={"number": export.number, "records": row_count},
    )
    return export


def make_export_event(export: ExportInfo, run_id: str) -> AuditEvent:
    """Return the audit event of an export (who, when, which number, draft or not)."""
    return AuditEvent(
        event=EXPORT_CREATED,
        run_id=run_id,
        by=export.exported_by,
        at=export.exported_at,
        details={
            "export_id": export.export_id,
            "number": export.number,
            "is_draft": export.is_draft,
        },
    )


def make_export_info(
    database: ReviewDatabase, run: RunInfo, run_folder: RunFolder, user: str, at: datetime
) -> ExportInfo:
    """Return the next export's info: number, draft or not, and its file references."""
    number = len(database.list_exports(run.run_id)) + 1
    is_draft = not run.is_verified
    names = make_export_file_names(run.name, number, is_draft)
    return ExportInfo(
        export_id=format_numbered_id(EXPORT_PREFIX, number),
        number=number,
        is_draft=is_draft,
        loader_file=run_folder.make_ref(run_folder.exports_dir / names.loader),
        audit_file=run_folder.make_ref(run_folder.exports_dir / names.audit),
        exported_at=at,
        exported_by=user,
    )


def write_export_files(
    database: ReviewDatabase,
    context: ExportContext,
    run_folder: RunFolder,
    run: RunInfo,
    export: ExportInfo,
) -> int:
    """Write the loader and the audit workbook; return the number of loader rows."""
    field_rules = context.review.config.field_rules
    records = database.read_records(run.run_id)
    run_folder.exports_dir.mkdir(parents=True, exist_ok=True)
    row_count = write_loader(
        context.template, field_rules, records, run_folder.resolve_ref(export.loader_file)
    )
    # Chunks resolve sources to documents and pages; a run without them still exports
    chunks = run_folder.read_chunks() if run_folder.chunks_file.is_file() else []
    source = AuditSource(
        run=run,
        export=export,
        records=records,
        issues=database.read_issues(run.run_id),
        changes=database.read_changes(run.run_id),
        documents=run_folder.read_documents(),
        chunks=chunks,
        field_rules=field_rules,
        models=context.models,
    )
    name_column = find_name_rule(field_rules).column
    audit_target = run_folder.resolve_ref(export.audit_file)
    write_audit_workbook(build_audit_rows(source), name_column, audit_target)
    return row_count
