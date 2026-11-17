"""Tests for what the model steps share: caches, the call budget, blank models, re-extraction.

All values are synthetic; field keys come from the client config, never written here.
"""

import sqlite3
from pathlib import Path

import pytest

from app.agents.step_support import CallBudget, InMemoryStepCache, make_step_cache_key
from app.config.bundle import ConfigBundle
from app.contracts.extraction import ExtractedField
from app.contracts.record import FieldVerification, StoredContextAttribute
from app.graph.context import BLANK_MODEL, capture_models
from app.graph.reextraction import find_reextraction_problems
from app.llm.fake_client import FakeLLMClient
from app.settings import MissingSettingError
from app.storage.review_db import (
    SCHEMA_VERSION,
    DatabaseStepCache,
    ReviewDatabase,
    ReviewDatabaseError,
)
from tests.integration.test_graph_model_steps import BlankModelClient
from tests.unit.record_helpers import make_record


def test_cache_key_does_not_depend_on_order_and_changes_with_any_part() -> None:
    """The same parts in any order give one key; a changed model or version gives another."""
    first = make_step_cache_key({"value": "a", "model": "m1", "prompt": "0.1"})
    assert first == make_step_cache_key({"prompt": "0.1", "model": "m1", "value": "a"})
    assert first != make_step_cache_key({"value": "a", "model": "m2", "prompt": "0.1"})
    assert first != make_step_cache_key({"value": "a", "model": "m1", "prompt": "0.2"})


def test_call_budget_stops_at_its_limit_and_none_means_no_limit() -> None:
    """A budget of two allows two calls; a blank limit (None) never stops."""
    budget = CallBudget(2)
    assert not budget.is_limit_reached()
    budget.record_call()
    budget.record_call()
    assert budget.is_limit_reached()
    unlimited = CallBudget(None)
    for _ in range(50):
        unlimited.record_call()
    assert not unlimited.is_limit_reached()


def test_memory_cache_returns_what_was_stored() -> None:
    """The in-memory cache gives back stored text, and None for an unknown key."""
    cache = InMemoryStepCache()
    assert cache.get("key") is None
    cache.put("key", "text")
    assert cache.get("key") == "text"


@pytest.mark.parametrize("table", ["matching_cache", "naming_cache", "plausibility_cache"])
def test_database_caches_survive_a_restart(tmp_path: Path, table: str) -> None:
    """Each step cache table keeps its results when the database is opened again."""
    path = tmp_path / "review.sqlite"
    DatabaseStepCache(ReviewDatabase(path), table).put("key-1", "synthetic text")
    assert DatabaseStepCache(ReviewDatabase(path), table).get("key-1") == "synthetic text"


def test_database_cache_refuses_a_table_that_is_not_a_step_cache(tmp_path: Path) -> None:
    """The table name goes into SQL, so only the three cache tables are accepted."""
    database = ReviewDatabase(tmp_path / "review.sqlite")
    with pytest.raises(ReviewDatabaseError, match="not a model step cache"):
        database.read_step_cache("runs", "key")


def test_database_from_the_old_schema_is_refused(tmp_path: Path) -> None:
    """A review database written before the step caches (version 2) is refused, not changed."""
    path = tmp_path / "review.sqlite"
    ReviewDatabase(path).close()
    connection = sqlite3.connect(path)
    connection.execute("UPDATE schema_info SET value = '2' WHERE key = 'schema_version'")
    connection.commit()
    connection.close()
    assert SCHEMA_VERSION == 3
    with pytest.raises(ReviewDatabaseError, match="schema version 2"):
        ReviewDatabase(path)


def test_blank_model_of_a_skippable_node_is_captured_as_blank() -> None:
    """Matching, Naming and plausibility with a blank model are captured as blank, not an error."""
    client = BlankModelClient({}, {"matching", "naming", "plausibility"})
    models = capture_models(client)
    assert {models[node] for node in ("matching", "naming", "plausibility")} == {BLANK_MODEL}
    assert models["extraction"] == FakeLLMClient({}).model


def test_blank_model_of_a_required_node_still_stops_the_run(bundle: ConfigBundle) -> None:
    """A blank extraction model raises MissingSettingError, as before."""
    client = BlankModelClient({}, {"extraction"})
    with pytest.raises(MissingSettingError):
        capture_models(client)


# ----- Re-extraction triggers (3.3) -----


def test_unverified_citation_on_a_context_attribute_triggers_reextraction(
    bundle: ConfigBundle,
) -> None:
    """A context attribute whose citation is not verified is a re-extraction problem."""
    rules = bundle.business_rules
    attribute = rules.context_fields()[0]
    record = make_record(rules)
    context = StoredContextAttribute(
        extraction=ExtractedField(status="found", value="synthetic heading"),
        verification=FieldVerification(citation_check="not_verified"),
    )
    record = record.model_copy(update={"context": {attribute.key: context}})
    [problem] = find_reextraction_problems([record], None)
    assert (problem.record_id, problem.field) == (record.record_id, attribute.key)


def test_unclear_status_alone_does_not_trigger_reextraction(bundle: ConfigBundle) -> None:
    """An unclear value (or context attribute) with a verified citation is not a problem."""
    rules = bundle.business_rules
    attribute = rules.context_fields()[0]
    unclear = ExtractedField(status="unclear", value="x", warning="synthetic")
    verified = FieldVerification(citation_check="verified")
    record = make_record(rules)
    field_key = rules.extracted_fields()[0].key
    stored = record.fields[field_key].model_copy(
        update={"extraction": unclear, "verification": verified}
    )
    context = StoredContextAttribute(extraction=unclear, verification=verified)
    record = record.model_copy(
        update={
            "fields": {**record.fields, field_key: stored},
            "context": {attribute.key: context},
        }
    )
    assert find_reextraction_problems([record], None) == []
