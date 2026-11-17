"""Wiring tests: the contexts the app builds use the live parts, not the test stand-ins.

Unit tests build contexts by hand with fakes, so they cannot notice a live factory that forgets
a real dependency. These tests build each context through its real factory and check the types.
"""

from pathlib import Path

from app.config.bundle import ConfigBundle
from app.llm.fake_client import FakeLLMClient
from app.runs.contexts import (
    LazyPlausibilityReviewer,
    load_export_context,
    make_processing_context,
    make_review_context,
)
from app.runs.workspace import Workspace
from app.settings import Settings
from app.storage.review_db import DatabaseJudgeCache, DatabaseStepCache, ReviewDatabase
from app.storage.run_store import RunStore
from app.validation.service import make_validation_config
from tests.integration.api_helpers import make_settings
from tests.unit.review_helpers import make_context, start_review
from tests.unit.validation_helpers import make_record


def make_workspace(tmp_path: Path, bundle: ConfigBundle, settings: Settings) -> Workspace:
    """Return a workspace on temporary stores, built the way the API builds it."""
    return Workspace(
        settings=settings,
        bundle=bundle,
        database=ReviewDatabase(tmp_path / "review.sqlite"),
        run_store=RunStore(tmp_path / "storage"),
        make_client=lambda: FakeLLMClient({}),
    )


def test_processing_context_uses_database_caches(tmp_path: Path, bundle: ConfigBundle) -> None:
    """The live processing context keeps the model step results in the database."""
    workspace = make_workspace(tmp_path, bundle, make_settings(tmp_path))
    context = make_processing_context(workspace, bundle.lookup_lists, None, FakeLLMClient({}))
    caches = context.step_caches
    assert isinstance(caches.matching, DatabaseStepCache)
    assert isinstance(caches.naming, DatabaseStepCache)
    assert isinstance(caches.plausibility, DatabaseStepCache)
    assert (caches.matching.table, caches.naming.table, caches.plausibility.table) == (
        "matching_cache",
        "naming_cache",
        "plausibility_cache",
    )
    assert isinstance(context.judge_cache, DatabaseJudgeCache)


def test_a_cached_result_outlives_the_context(tmp_path: Path, bundle: ConfigBundle) -> None:
    """A result stored through one processing context is found through a new one."""
    workspace = make_workspace(tmp_path, bundle, make_settings(tmp_path))
    first = make_processing_context(workspace, bundle.lookup_lists, None, FakeLLMClient({}))
    first.step_caches.naming.put("key-1", "synthetic text")
    second = make_processing_context(workspace, bundle.lookup_lists, None, FakeLLMClient({}))
    assert second.step_caches.naming.get("key-1") == "synthetic text"


def test_processing_context_carries_the_limits_and_shortlist_setting(
    tmp_path: Path, bundle: ConfigBundle
) -> None:
    """The settings reach the limits the graph reads (a blank one stays blank)."""
    settings = make_settings(
        tmp_path, max_matching_calls=3, max_naming_calls=4, max_plausibility_calls=5
    )
    workspace = make_workspace(tmp_path, bundle, settings)
    limits = make_processing_context(workspace, bundle.lookup_lists, None, FakeLLMClient({})).limits
    assert (limits.max_matching_calls, limits.max_naming_calls) == (3, 4)
    assert limits.max_plausibility_calls == 5
    assert limits.matching_shortlist_size is None


def test_review_and_export_contexts_carry_the_plausibility_reviewer(
    tmp_path: Path, bundle: ConfigBundle
) -> None:
    """A re-check and an export, built the live way, run the plausibility review."""
    workspace = make_workspace(tmp_path, bundle, make_settings(tmp_path))
    context = make_context(make_validation_config(bundle))
    start_review(tmp_path, bundle, context, [make_record(bundle)])
    run = workspace.database.read_run("run_0001")
    review = make_review_context(workspace, run)
    assert isinstance(review.plausibility, LazyPlausibilityReviewer)
    export = load_export_context(workspace, "run_0001")
    assert isinstance(export.review.plausibility, LazyPlausibilityReviewer)


def test_lookup_admin_gets_the_shortlist_setting(tmp_path: Path, bundle: ConfigBundle) -> None:
    """The admin the API builds checks uploads against the configured shortlist size."""
    workspace = make_workspace(tmp_path, bundle, make_settings(tmp_path, matching_shortlist_size=7))
    assert workspace.lookup_admin().shortlist_size == 7
