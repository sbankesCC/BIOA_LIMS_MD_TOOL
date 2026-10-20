"""Builds the processing, review and export contexts of one run from its captured versions.

A run uses the lookup lists and reference data captured at its start for its whole life
(ARCHITECTURE §6). The duplicate judge's LLM client is only built when the judge is called,
so saving changes and re-checks without judge calls work without the LLM settings.
"""

from collections.abc import Callable

from app.agents.duplicate_judge import DuplicateJudgeAgent
from app.config.lookup_lists import LookupLists
from app.contracts.judge import JudgeOutput
from app.contracts.reference import ReferenceData
from app.contracts.run import RunInfo
from app.export.service import ExportContext
from app.graph.context import (
    JUDGE_PROMPT,
    ProcessingContext,
    make_run_versions,
    read_processing_limits,
)
from app.llm.client import LLMClient
from app.llm.tracing import TracedCaller
from app.review.service import ReviewContext
from app.runs.workspace import Workspace
from app.storage.review_db import DatabaseJudgeCache
from app.validation.judge_cache import DuplicateJudge, JudgeRequest
from app.validation.service import make_validation_config


class LazyDuplicateJudge:
    """A duplicate judge that builds the real one (and its LLM client) on its first call."""

    def __init__(self, build_judge: Callable[[], DuplicateJudge]) -> None:
        """Remember how to build the judge; nothing is built yet."""
        self.build_judge = build_judge
        self.judge_agent: DuplicateJudge | None = None

    def judge(self, request: JudgeRequest) -> JudgeOutput:
        """Build the judge if needed, then pass the request on."""
        if self.judge_agent is None:
            self.judge_agent = self.build_judge()
        return self.judge_agent.judge(request)


def make_processing_context(
    workspace: Workspace,
    lookup_lists: LookupLists,
    reference: ReferenceData | None,
    client: LLMClient,
) -> ProcessingContext:
    """Return the context the graph processes a new run with; LLM_RETRIES must be set."""
    return ProcessingContext(
        bundle=workspace.bundle,
        lookup_lists=lookup_lists,
        reference=reference,
        client=client,
        run_store=workspace.run_store,
        database=workspace.database,
        judge_cache=DatabaseJudgeCache(workspace.database),
        limits=read_processing_limits(workspace.settings),
    )


def make_review_context(workspace: Workspace, run: RunInfo) -> ReviewContext:
    """Return the review context of a run, with the lookup lists and reference data it captured."""
    lookup_lists = workspace.lookup_admin().load_lookup_lists(run.config_versions.lookup_lists)
    reference = workspace.reference_admin().load_reference_data(run.reference_data_version)
    template = workspace.bundle.prompts[JUDGE_PROMPT]
    return ReviewContext(
        config=make_validation_config(workspace.bundle, lookup_lists),
        judge=LazyDuplicateJudge(lambda: make_judge_agent(workspace, run)),
        judge_cache=DatabaseJudgeCache(workspace.database),
        judge_prompt_version=template.version,
        judge_call_limit=workspace.settings.max_duplicate_judge_calls,
        reference=reference,
    )


def load_review_context(workspace: Workspace, run_id: str) -> ReviewContext:
    """Return the review context of a stored run; raise RunNotFoundError if it is not stored."""
    return make_review_context(workspace, workspace.database.read_run(run_id))


def make_judge_agent(workspace: Workspace, run: RunInfo) -> DuplicateJudgeAgent:
    """Build the LLM duplicate judge of a run; LLM_PROVIDER and LLM_RETRIES must be set."""
    retries = workspace.settings.require_integer("LLM_RETRIES")
    folder = workspace.run_store.open_run(run.run_id)
    caller = TracedCaller(workspace.make_client(), folder, make_run_versions(run), retries)
    template = workspace.bundle.prompts[JUDGE_PROMPT]
    return DuplicateJudgeAgent(caller, run.run_id, template, workspace.bundle.field_rules)


def load_export_context(workspace: Workspace, run_id: str) -> ExportContext:
    """Return the export context of a stored run: its review context, the template, its models."""
    run = workspace.database.read_run(run_id)
    return ExportContext(
        review=make_review_context(workspace, run),
        template=workspace.bundle.dfd_template,
        models=run.models,
    )
