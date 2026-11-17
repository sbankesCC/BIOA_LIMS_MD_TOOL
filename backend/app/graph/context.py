"""Processing context: everything the graph's nodes use besides the state, built once per run.

The run's captured config (lookup list and reference data versions) goes in here, so the run
uses the same versions for its whole life (ARCHITECTURE §6). Limits come from the settings.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from PIL import Image
from pydantic import BaseModel

from app.agents.duplicate_judge import DuplicateJudgeAgent
from app.agents.plausibility import PlausibilityAgent
from app.agents.step_support import CallBudget, InMemoryStepCache, StepCache
from app.config.bundle import ConfigBundle
from app.config.lookup_lists import LookupLists
from app.contracts.reference import ReferenceData
from app.contracts.run import RunInfo
from app.contracts.trace import LlmNode
from app.llm.client import LLMClient
from app.llm.tracing import TracedCaller
from app.settings import MissingSettingError, Settings
from app.storage.review_db import ReviewDatabase
from app.storage.run_store import RunFolder, RunStore
from app.validation.judge_cache import JudgeCache, JudgeRunner

# Every node that calls the LLM, in flow order (the models captured per run)
LLM_NODES: tuple[LlmNode, ...] = (
    "extraction",
    "extraction_verification",
    "matching",
    "naming",
    "plausibility",
    "duplicate_judge",
)

# Nodes that never fail a run: a blank model setting skips them instead (model captured as blank)
SKIPPABLE_NODES: tuple[LlmNode, ...] = ("matching", "naming", "plausibility")
BLANK_MODEL = ""

# Prompt templates of the duplicate judge and the plausibility review
JUDGE_PROMPT = "duplicate_judge"
PLAUSIBILITY_PROMPT = "plausibility"

# Reference data version written to traces when the run has none
NO_REFERENCE_DATA = "none"


class ProcessingLimits(BaseModel):
    """Limits from the settings: LLM retries, the input token cap, re-extractions, judge calls."""

    llm_retries: int
    max_reextract: int
    max_input_tokens: int | None = None
    max_duplicate_judge_calls: int | None = None
    max_matching_calls: int | None = None
    max_naming_calls: int | None = None
    max_plausibility_calls: int | None = None
    matching_shortlist_size: int | None = None


def read_processing_limits(settings: Settings) -> ProcessingLimits:
    """Read the limits; LLM_RETRIES has no blank meaning, so it raises MissingSettingError."""
    return ProcessingLimits(
        llm_retries=settings.require_integer("LLM_RETRIES"),
        max_reextract=settings.max_reextract,
        max_input_tokens=settings.max_input_tokens,
        max_duplicate_judge_calls=settings.max_duplicate_judge_calls,
        max_matching_calls=settings.max_matching_calls,
        max_naming_calls=settings.max_naming_calls,
        max_plausibility_calls=settings.max_plausibility_calls,
        matching_shortlist_size=settings.matching_shortlist_size,
    )


@dataclass(frozen=True)
class StepCaches:
    """The result caches of the three model steps that never fail a run."""

    matching: StepCache
    naming: StepCache
    plausibility: StepCache


def make_memory_caches() -> StepCaches:
    """Return caches that live as long as the context (tests and evals)."""
    return StepCaches(InMemoryStepCache(), InMemoryStepCache(), InMemoryStepCache())


@dataclass(frozen=True)
class ProcessingContext:
    """What the nodes use: config, the run's lookup lists and reference data, stores, LLM."""

    bundle: ConfigBundle
    lookup_lists: LookupLists
    reference: ReferenceData | None
    client: LLMClient
    run_store: RunStore
    database: ReviewDatabase
    judge_cache: JudgeCache
    limits: ProcessingLimits
    step_caches: StepCaches


def capture_models(client: LLMClient) -> dict[str, str]:
    """Return the model of every LLM node.

    A blank model setting raises MissingSettingError, except for Matching, Naming and the
    plausibility review: they are captured as blank and the step is skipped.
    """
    return {node: read_model(client, node) or BLANK_MODEL for node in LLM_NODES}


def read_model(client: LLMClient, node: LlmNode) -> str | None:
    """Return a node's model; a skippable node with a blank setting gives None."""
    try:
        return client.model_for(node)
    except MissingSettingError:
        if node in SKIPPABLE_NODES:
            return None
        raise


def make_run_versions(run: RunInfo) -> dict[str, str]:
    """Return a run's captured config versions as flat text (prompts are traced per call)."""
    versions = run.config_versions.model_dump(exclude={"prompts"})
    versions["reference_data"] = run.reference_data_version or NO_REFERENCE_DATA
    return {name: str(value) for name, value in versions.items()}


def make_caller(
    context: ProcessingContext, folder: RunFolder, versions: Mapping[str, str]
) -> TracedCaller:
    """Return a traced LLM caller for one run."""
    return TracedCaller(context.client, folder, versions, context.limits.llm_retries)


def make_judge_runner(context: ProcessingContext, caller: TracedCaller, run_id: str) -> JudgeRunner:
    """Return the duplicate judge runner for one validation pass of a run."""
    template = context.bundle.prompts[JUDGE_PROMPT]
    judge = DuplicateJudgeAgent(caller, run_id, template, context.bundle.business_rules)
    return JudgeRunner(
        judge, context.judge_cache, template.version, context.limits.max_duplicate_judge_calls
    )


def make_plausibility_reviewer(
    context: ProcessingContext, caller: TracedCaller, run_id: str
) -> PlausibilityAgent:
    """Return the plausibility reviewer for one validation pass of a run."""
    return PlausibilityAgent(
        caller,
        run_id,
        context.bundle.business_rules,
        context.bundle.prompts[PLAUSIBILITY_PROMPT],
        read_model(context.client, "plausibility"),
        context.step_caches.plausibility,
        CallBudget(context.limits.max_plausibility_calls),
    )


def read_image_size(run_store: RunStore, image_ref: str) -> tuple[int, int]:
    """Return a stored page image's (width, height) in pixels."""
    with Image.open(run_store.resolve_ref(image_ref)) as image:
        return image.size
