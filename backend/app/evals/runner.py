"""Eval runner: runs each case's documents through the same processing graph the app runs.

Each run gets its own run ID in a work folder (run store, review DB, checkpoints) that never
touches the app's data folders. A case with a `fake_llm/` folder uses its fake replies unless
the real provider is asked for; other cases use the provider from LLM_PROVIDER.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from app.config.bundle import ConfigBundle
from app.contracts.chunk import Chunk
from app.contracts.eval_case import SeededError
from app.contracts.record import StoredRecord
from app.contracts.verification import FieldFinding
from app.evals.case_loader import EvalCase
from app.evals.scoring import ActualRecord, ActualSource, collect_field_findings
from app.evals.seeding import EvalLLMClient
from app.graph.build import make_run_info, run_processing
from app.graph.context import ProcessingContext, ProcessingLimits, read_processing_limits
from app.ids import IdCounter
from app.llm.client import LLMClient
from app.llm.fake_client import FakeLLMClient, load_fake_replies
from app.llm.provider import make_llm_client
from app.settings import Settings
from app.storage.review_db import ReviewDatabase
from app.storage.run_store import DocumentInfo, RunStore
from app.validation.judge_cache import InMemoryJudgeCache

# Who eval runs are created by, and how their run IDs start
EVAL_USER = "eval harness"
EVAL_RUN_PREFIX = "run_eval_"

# Fake replies are written for this flow: no retries, the documented one re-extraction, no caps
FAKE_LIMITS = ProcessingLimits(llm_retries=0, max_reextract=1)

# Work folder contents
STORAGE_FOLDER = "storage"
REVIEW_DB_FILE = "review.sqlite"
CHECKPOINT_FILE = "checkpoints.sqlite"


class RunOutcome(BaseModel):
    """What one eval run produced: status, records for scoring, findings and planted errors."""

    run_id: str
    status: str
    error: str | None = None
    records: list[ActualRecord] = []
    findings: list[FieldFinding] = []
    planted: list[SeededError] = []


class CaseOutcome(BaseModel):
    """Every run of one case, with the provider and models it ran with."""

    provider: str
    models: dict[str, str]
    runs: list[RunOutcome]


@dataclass
class EvalWorkspace:
    """The stores eval runs use, all inside one work folder, plus the run ID counter."""

    run_store: RunStore
    database: ReviewDatabase
    checkpoint_path: Path
    run_ids: IdCounter

    def close(self) -> None:
        """Close the review database."""
        self.database.close()


def open_workspace(work_dir: Path) -> EvalWorkspace:
    """Create the run store, review DB and checkpoint path inside the work folder."""
    work_dir.mkdir(parents=True, exist_ok=True)
    return EvalWorkspace(
        run_store=RunStore(work_dir / STORAGE_FOLDER),
        database=ReviewDatabase(work_dir / REVIEW_DB_FILE),
        checkpoint_path=work_dir / CHECKPOINT_FILE,
        run_ids=IdCounter(EVAL_RUN_PREFIX),
    )


def is_fake_case(case: EvalCase, use_real_llm: bool) -> bool:
    """Return True when the case runs on its fake replies."""
    return case.fake_llm_folder is not None and not use_real_llm


def make_case_client(
    case: EvalCase, settings: Settings, storage_dir: Path, use_real_llm: bool
) -> LLMClient:
    """Return a fresh client for one run: the case's fake replies, or the configured provider."""
    if is_fake_case(case, use_real_llm) and case.fake_llm_folder is not None:
        return FakeLLMClient(load_fake_replies(case.fake_llm_folder))
    return make_llm_client(settings, storage_dir)


def make_case_limits(settings: Settings, is_fake: bool) -> ProcessingLimits:
    """Return the fixed limits for fake replies, else the limits from the settings."""
    if is_fake:
        return FAKE_LIMITS
    return read_processing_limits(settings)


def run_case(
    case: EvalCase,
    bundle: ConfigBundle,
    settings: Settings,
    workspace: EvalWorkspace,
    runs: int,
    use_real_llm: bool = False,
) -> CaseOutcome:
    """Run one case `runs` times through the graph, each run on its own fresh client."""
    limits = make_case_limits(settings, is_fake_case(case, use_real_llm))
    outcomes: list[RunOutcome] = []
    client: LLMClient | None = None
    for _ in range(runs):
        client = make_case_client(case, settings, workspace.run_store.storage_dir, use_real_llm)
        outcomes.append(run_once(case, bundle, client, limits, workspace))
    if client is None:
        return CaseOutcome(provider="", models={}, runs=[])
    models = workspace.database.read_run(outcomes[0].run_id).models
    return CaseOutcome(provider=client.provider, models=models, runs=outcomes)


def run_once(
    case: EvalCase,
    bundle: ConfigBundle,
    client: LLMClient,
    limits: ProcessingLimits,
    workspace: EvalWorkspace,
) -> RunOutcome:
    """Store the case's documents as a new run, process it, and describe the result."""
    run_id = workspace.run_ids.next_id()
    eval_client = EvalLLMClient(client, case.seeded.errors, bundle.field_rules)
    start_run(case, bundle, eval_client, workspace, run_id)
    context = ProcessingContext(
        bundle=bundle,
        lookup_lists=bundle.lookup_lists,
        reference=None,
        client=eval_client,
        run_store=workspace.run_store,
        database=workspace.database,
        judge_cache=InMemoryJudgeCache(),
        limits=limits,
    )
    error: str | None = None
    # A failing run is reported with its error; the other runs and cases go on
    try:
        run_processing(context, run_id, workspace.checkpoint_path)
    except Exception as exception:
        error = f"{type(exception).__name__}: {exception}"
    return describe_outcome(workspace, bundle, run_id, error, eval_client)


def start_run(
    case: EvalCase,
    bundle: ConfigBundle,
    client: LLMClient,
    workspace: EvalWorkspace,
    run_id: str,
) -> None:
    """Add the run (seed lookup lists, no reference data) and upload the case's documents."""
    run = make_run_info(
        run_id,
        case.info.id,
        EVAL_USER,
        datetime.now(UTC),
        bundle,
        bundle.lookup_lists,
        None,
        client,
    )
    workspace.database.add_run(run)
    folder = workspace.run_store.create_run(run_id)
    for document in case.documents:
        folder.save_upload(document.name, document.read_bytes())


def describe_outcome(
    workspace: EvalWorkspace,
    bundle: ConfigBundle,
    run_id: str,
    error: str | None,
    client: EvalLLMClient,
) -> RunOutcome:
    """Read a processed run back from the stores as a RunOutcome."""
    folder = workspace.run_store.open_run(run_id)
    records = workspace.database.read_records(run_id)
    chunks = folder.read_chunks() if folder.chunks_file.is_file() else []
    name_key = bundle.field_rules.record_name_field().key
    return RunOutcome(
        run_id=run_id,
        status=workspace.database.read_run(run_id).status,
        error=error,
        records=describe_records(records, chunks, folder.read_documents(), name_key),
        findings=collect_field_findings(client.verification_texts),
        planted=client.planted,
    )


def describe_records(
    records: Sequence[StoredRecord],
    chunks: Sequence[Chunk],
    documents: Sequence[DocumentInfo],
    name_key: str,
) -> list[ActualRecord]:
    """Turn stored records into scoring records: name, sources, extraction and output values."""
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    names_by_document = {document.document_id: document.file_name for document in documents}
    return [
        ActualRecord(
            record_id=record.record_id,
            name=read_record_name(record, name_key),
            sources=describe_sources(record.found_in, chunks_by_id, names_by_document),
            fields={key: field.extraction for key, field in record.fields.items()},
            output_values={key: field.output.value for key, field in record.fields.items()},
        )
        for record in records
    ]


def read_record_name(record: StoredRecord, name_key: str) -> str | None:
    """Return the record's name as extracted, else its output value."""
    field = record.fields.get(name_key)
    if field is None:
        return None
    if field.extraction is not None and isinstance(field.extraction.value, str):
        return field.extraction.value
    return field.output.value


def describe_sources(
    chunk_ids: Sequence[str], chunks_by_id: dict[str, Chunk], names_by_document: dict[str, str]
) -> list[ActualSource]:
    """Resolve "found in" chunk IDs to document file name, page, section and sheet."""
    sources: list[ActualSource] = []
    for chunk_id in chunk_ids:
        chunk = chunks_by_id.get(chunk_id)
        if chunk is None:
            continue
        sources.append(
            ActualSource(
                document=names_by_document.get(chunk.document_id, chunk.document_id),
                page=chunk.page,
                section=chunk.section,
                sheet=chunk.sheet,
            )
        )
    return sources
