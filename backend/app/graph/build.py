"""Graph assembly and running: nodes plus the edges from `routing.py`, with a SQLite checkpointer.

One run is one LangGraph thread (`thread_id` = `run_id`). `make_run_info` captures a new run's
config versions and models; `run_processing` runs the graph to `in_review` or `failed`. The API
(M9) calls `run_processing` in a background thread.
"""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from functools import partial
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

# LangGraph ships without type stubs for these modules; its own signatures hold unknown parts
from langgraph.graph import StateGraph  # pyright: ignore[reportMissingTypeStubs]
from langgraph.graph.state import CompiledStateGraph  # pyright: ignore[reportMissingTypeStubs]

from app.config.bundle import ConfigBundle
from app.config.lookup_lists import LookupLists
from app.contracts.reference import ReferenceData
from app.contracts.run import RunInfo, RunStatus
from app.graph import nodes, routing
from app.graph.context import ProcessingContext, capture_models, make_run_versions
from app.graph.state import ProcessingState, make_initial_state
from app.llm.client import LLMClient
from app.logging_setup import log_event

# Each node with the status the run shows while it works (None: the node sets its own)
NODES: list[tuple[str, RunStatus | None, nodes.NodeFunction]] = [
    (routing.INGEST, "ingesting", nodes.ingest_node),
    (routing.EXTRACTION, "extracting", nodes.extraction_node),
    (routing.VERIFICATION, "verifying_extraction", nodes.verification_node),
    (routing.TRANSFORMATION, "transforming", nodes.transformation_node),
    (routing.VALIDATION, "validating", nodes.validation_node),
    (routing.FINISH, None, nodes.finish_node),
    (routing.FAILED, None, nodes.failed_node),
]

# Steps LangGraph may take: the straight path plus two per allowed re-extraction
BASE_STEP_LIMIT = 20
STEPS_PER_REEXTRACTION = 2


def make_run_info(
    run_id: str,
    name: str,
    user: str,
    at: datetime,
    bundle: ConfigBundle,
    lookup_lists: LookupLists,
    reference: ReferenceData | None,
    client: LLMClient,
    retry_of: str | None = None,
) -> RunInfo:
    """Capture a new run's config versions, reference data version and models at its start."""
    versions = bundle.versions().model_copy(update={"lookup_lists": lookup_lists.version})
    return RunInfo(
        run_id=run_id,
        name=name,
        created_by=user,
        created_at=at,
        config_versions=versions,
        reference_data_version=reference.version if reference is not None else None,
        models=capture_models(client),
        retry_of=retry_of,
    )


def build_graph(context: ProcessingContext) -> StateGraph[ProcessingState]:
    """Add every node (bound to the context) and every edge rule from `routing.py`."""
    graph = StateGraph(ProcessingState)
    for name, status, node in NODES:
        action = partial(nodes.run_node, name, status, node, context=context)
        graph.add_node(name, action)  # pyright: ignore[reportUnknownMemberType]
    for source, destination in routing.FIXED_EDGES:
        graph.add_edge(source, destination)
    for source, rule, destinations in routing.CONDITIONAL_EDGES:
        graph.add_conditional_edges(source, rule, destinations)
    return graph


@contextmanager
def open_checkpointer(path: Path) -> Generator[SqliteSaver]:
    """Open the SQLite checkpointer at CHECKPOINT_DB's path; closed when the block ends."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), check_same_thread=False)
    try:
        yield SqliteSaver(connection)
    finally:
        connection.close()


def compile_graph(
    context: ProcessingContext, checkpointer: SqliteSaver
) -> CompiledStateGraph[ProcessingState]:
    """Build and compile the graph with the checkpointer."""
    return build_graph(context).compile(checkpointer=checkpointer)  # pyright: ignore[reportUnknownMemberType]


def run_processing(context: ProcessingContext, run_id: str, checkpoint_path: Path) -> None:
    """Process a stored run from ingest to `in_review` (or `failed`), checkpointing each step.

    An unexpected error marks the run `failed` and is raised again for the caller to report.
    """
    run = context.database.read_run(run_id)
    state = make_initial_state(run_id, make_run_versions(run), context.limits.max_reextract)
    step_limit = BASE_STEP_LIMIT + STEPS_PER_REEXTRACTION * context.limits.max_reextract
    log_event("run_started", run_id=run_id)
    try:
        with open_checkpointer(checkpoint_path) as checkpointer:
            graph = compile_graph(context, checkpointer)
            graph.invoke(  # pyright: ignore[reportUnknownMemberType]
                state, {"configurable": {"thread_id": run_id}, "recursion_limit": step_limit}
            )
    except Exception:
        context.database.set_run_status(run_id, "failed")
        log_event("node_failed", level="ERROR", run_id=run_id)
        raise
