"""Builds the processing, review and export contexts of one run from its captured versions.

A run uses the lookup lists and reference data captured at its start for its whole life
(ARCHITECTURE §6). The duplicate judge's LLM client is only built when the judge is called,
so saving changes and re-checks without judge calls work without the LLM settings.
"""

from collections.abc import Callable

from app.agents.duplicate_judge import DuplicateJudgeAgent
from app.agents.plausibility import (
    PlausibilityAgent,
    PlausibilityResult,
    find_active_check_ids,
)
from app.agents.step_support import CallBudget
from app.config.business_rules import BusinessRules
from app.config.lookup_lists import LookupLists
from app.contracts.judge import JudgeOutput
from app.contracts.plausibility import PlausibilityRecord
from app.contracts.reference import ReferenceData
from app.contracts.run import RunInfo
from app.export.service import ExportContext
from app.graph.context import (
    JUDGE_PROMPT,
    PLAUSIBILITY_PROMPT,
    ProcessingContext,
    StepCaches,
    make_run_versions,
    read_processing_limits,
)
from app.llm.client import LLMClient
from app.llm.tracing import TracedCaller
from app.review.service import ReviewContext
from app.runs.workspace import Workspace
from app.settings import MissingSettingError
from app.storage.review_db import DatabaseJudgeCache, DatabaseStepCache
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


class LazyPlausibilityReviewer:
    """A plausibility reviewer that builds the real one (and its LLM client) when first needed.

    No active check means no model and no client. A missing LLM setting skips the review (the
    review never fails a re-check): the result says so, and validation adds the run warning.
    """

    def __init__(
        self, build_agent: Callable[[], PlausibilityAgent], business_rules: BusinessRules
    ) -> None:
        """Remember how to build the agent and the rules that say whether a check is active."""
        self.build_agent = build_agent
        self.business_rules = business_rules
        self.agent: PlausibilityAgent | None = None

    def review(self, records: list[PlausibilityRecord]) -> PlausibilityResult:
        """Review the records, building the agent on first use."""
        if not records or not find_active_check_ids(self.business_rules):
            return PlausibilityResult()
        try:
            if self.agent is None:
                self.agent = self.build_agent()
        except MissingSettingError:
            return PlausibilityResult(is_skipped=True)
        return self.agent.review(records)


def make_database_caches(workspace: Workspace) -> StepCaches:
    """Return the Matching, Naming and plausibility caches kept in the review database."""
    database = workspace.database
    return StepCaches(
        DatabaseStepCache(database, "matching_cache"),
        DatabaseStepCache(database, "naming_cache"),
        DatabaseStepCache(database, "plausibility_cache"),
    )


def make_plausibility_agent(workspace: Workspace, run: RunInfo) -> PlausibilityAgent:
    """Build the plausibility reviewer of a run; LLM_PROVIDER and LLM_RETRIES must be set.

    The model is the one the run captured at its start (blank means the step was off).
    """
    retries = workspace.settings.require_integer("LLM_RETRIES")
    folder = workspace.run_store.open_run(run.run_id)
    caller = TracedCaller(workspace.make_client(), folder, make_run_versions(run), retries)
    return PlausibilityAgent(
        caller,
        run.run_id,
        workspace.bundle.business_rules,
        workspace.bundle.prompts[PLAUSIBILITY_PROMPT],
        run.models.get("plausibility") or None,
        DatabaseStepCache(workspace.database, "plausibility_cache"),
        CallBudget(workspace.settings.max_plausibility_calls),
    )


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
        step_caches=make_database_caches(workspace),
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
        plausibility=LazyPlausibilityReviewer(
            lambda: make_plausibility_agent(workspace, run), workspace.bundle.business_rules
        ),
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
    return DuplicateJudgeAgent(caller, run.run_id, template, workspace.bundle.business_rules)


def load_export_context(workspace: Workspace, run_id: str) -> ExportContext:
    """Return the export context of a stored run: its review context, the template, its models."""
    run = workspace.database.read_run(run_id)
    return ExportContext(
        review=make_review_context(workspace, run),
        template=workspace.bundle.export_template,
        models=run.models,
    )
