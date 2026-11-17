"""Graph tests for Matching, Naming and the plausibility review: suggestions, skips and caches.

All replies and values are synthetic. Field keys, lookup values and rule IDs are read from the
client config, never written here.
"""

import json
from pathlib import Path

import pytest

from app.config.bundle import ConfigBundle
from app.config.business_rules import BusinessRules, FieldDefinition
from app.contracts.trace import LlmNode
from app.graph.build import open_checkpointer
from app.graph.context import ProcessingLimits, make_memory_caches
from app.llm.fake_client import FakeLLMClient, FakeReply
from app.llm.tracing import read_traces
from app.settings import MissingSettingError
from tests.fixtures.fake_llm import (
    extraction_reply,
    matching_reply,
    naming_reply,
    plausibility_reply,
    verification_reply,
)
from tests.integration.test_graph import NAMES, RUN_ID, TWO_ROWS, GraphRun, process_run

UNRESOLVED_TEXT = "synthetic cold room"


class BlankModelClient(FakeLLMClient):
    """A fake client whose model setting is blank for some nodes, as an unset env var is."""

    def __init__(self, replies: dict[str, list[FakeReply]], blank_nodes: set[LlmNode]) -> None:
        """Keep the replies and the nodes whose model is blank."""
        super().__init__(replies)
        self.blank_nodes = blank_nodes

    def model_for(self, node: LlmNode) -> str:
        """Raise the missing-setting error for a blank node, like the OpenAI client does."""
        if node in self.blank_nodes:
            raise MissingSettingError(f"{node.upper()}_MODEL")
        return super().model_for(node)


def matching_field(bundle: ConfigBundle) -> FieldDefinition:
    """Return a field that allows Matching and has a lookup list."""
    return next(
        rule
        for rule in bundle.business_rules.extracted_fields()
        if rule.matching_allowed and rule.lookup_sheet is not None
    )


def replies_with_unresolved(bundle: ConfigBundle) -> dict[str, list[FakeReply]]:
    """Return replies where both records hold a value no list value matches."""
    field = matching_field(bundle)
    found = {field.key: UNRESOLVED_TEXT}
    return {
        "extraction": [extraction_reply(bundle.business_rules, TWO_ROWS, found)],
        "extraction_verification": [verification_reply()],
        "naming": [naming_reply(NAMES)],
    }


def first_list_value(bundle: ConfigBundle, field: FieldDefinition) -> str:
    """Return the first value of the field's lookup list."""
    assert field.lookup_sheet is not None
    return bundle.lookup_lists.sheets[field.lookup_sheet][0]


def issue_codes(run: GraphRun) -> list[str]:
    """Return the codes of the run's open issues."""
    return run.issue_codes()


# ----- Matching -----


def test_matching_makes_one_call_and_stores_a_suggestion_only(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """Two records with the same unresolved value give one item; the choice is not applied."""
    field = matching_field(bundle)
    choice = first_list_value(bundle, field)
    replies = replies_with_unresolved(bundle)
    replies["matching"] = [matching_reply([("m_0001", choice)])]
    run = process_run(tmp_path, bundle, synthetic_documents, replies)
    assert len(run.client.calls_for("matching")) == 1
    for record in run.database.read_records(RUN_ID):
        stored = record.fields[field.key]
        assert stored.suggestion is not None
        assert (stored.suggestion.value, stored.suggestion.source) == (choice, "matching")
        # The value stays empty until a person uses the suggestion
        assert stored.output.value is None
    assert "MATCHING_SKIPPED" not in issue_codes(run)


def test_matching_choice_off_the_shortlist_is_rejected(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """A choice that is not on the item's shortlist stores no suggestion."""
    field = matching_field(bundle)
    replies = replies_with_unresolved(bundle)
    replies["matching"] = [matching_reply([("m_0001", "Synthetic Not On The List")])]
    run = process_run(tmp_path, bundle, synthetic_documents, replies)
    for record in run.database.read_records(RUN_ID):
        assert record.fields[field.key].suggestion is None


def test_matching_shortlist_is_cut_to_the_setting(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """MATCHING_SHORTLIST_SIZE limits how many list values each item shows."""
    field = matching_field(bundle)
    replies = replies_with_unresolved(bundle)
    replies["matching"] = [matching_reply([("m_0001", None)])]
    limits = ProcessingLimits(llm_retries=1, max_reextract=1, matching_shortlist_size=2)
    run = process_run(tmp_path, bundle, synthetic_documents, replies, limits=limits)
    [request] = run.client.calls_for("matching")
    text = "".join(getattr(part, "text", "") for part in request.parts)
    line = next(item for item in text.splitlines() if item.startswith('{"item_id": "m_0001", "f'))
    assert len(json.loads(line)["shortlist"]) == 2
    assert json.loads(line)["field"] == field.column


def test_matching_is_not_called_when_nothing_is_unresolved(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """No unresolved values: no call and no warning."""
    replies = replies_with_unresolved(bundle)
    replies["extraction"] = [extraction_reply(bundle.business_rules, TWO_ROWS)]
    run = process_run(tmp_path, bundle, synthetic_documents, replies)
    assert run.client.calls_for("matching") == []
    assert "MATCHING_SKIPPED" not in issue_codes(run)


# ----- The skipped steps -----


def blank_client(replies: dict[str, list[FakeReply]], node: LlmNode) -> FakeLLMClient:
    """Return a client whose model for one node is blank."""
    return BlankModelClient(replies, {node})


@pytest.mark.parametrize(
    ("node", "code"), [("matching", "MATCHING_SKIPPED"), ("naming", "NAMING_SKIPPED")]
)
def test_blank_model_skips_the_step_with_a_warning(
    tmp_path: Path,
    bundle: ConfigBundle,
    synthetic_documents: dict[str, Path],
    node: LlmNode,
    code: str,
) -> None:
    """A blank model setting skips the step: no call, a run warning, and the run still ends."""
    replies = replies_with_unresolved(bundle)
    replies["matching"] = [matching_reply([("m_0001", None)])]
    run = process_run(
        tmp_path, bundle, synthetic_documents, replies, client=blank_client(replies, node)
    )
    assert run.client.calls_for(node) == []
    assert code in issue_codes(run)
    assert run.database.read_run(RUN_ID).status == "in_review"
    assert run.database.read_run(RUN_ID).models[node] == ""


@pytest.mark.parametrize(
    ("node", "code"), [("matching", "MATCHING_SKIPPED"), ("naming", "NAMING_SKIPPED")]
)
def test_reached_call_limit_skips_the_step_with_a_warning(
    tmp_path: Path,
    bundle: ConfigBundle,
    synthetic_documents: dict[str, Path],
    node: LlmNode,
    code: str,
) -> None:
    """A call limit of zero skips the step before any call."""
    replies = replies_with_unresolved(bundle)
    replies["matching"] = [matching_reply([("m_0001", None)])]
    limits = ProcessingLimits(
        llm_retries=1,
        max_reextract=1,
        max_matching_calls=0 if node == "matching" else None,
        max_naming_calls=0 if node == "naming" else None,
    )
    run = process_run(tmp_path, bundle, synthetic_documents, replies, limits=limits)
    assert run.client.calls_for(node) == []
    assert code in issue_codes(run)


@pytest.mark.parametrize(
    ("node", "code"), [("matching", "MATCHING_SKIPPED"), ("naming", "NAMING_SKIPPED")]
)
def test_call_that_fails_after_its_retry_skips_the_step(
    tmp_path: Path,
    bundle: ConfigBundle,
    synthetic_documents: dict[str, Path],
    node: LlmNode,
    code: str,
) -> None:
    """Two answers that break the schema skip the step; the run is not failed."""
    replies = replies_with_unresolved(bundle)
    replies[node] = ["synthetic: not JSON", "{}"]
    run = process_run(tmp_path, bundle, synthetic_documents, replies)
    assert len(run.client.calls_for(node)) == 2
    assert code in issue_codes(run)
    assert run.database.read_run(RUN_ID).status == "in_review"
    statuses = [
        trace.status for trace in read_traces(run.run_store.open_run(RUN_ID)) if trace.node == node
    ]
    assert statuses == ["schema_violation", "schema_violation"]


# ----- Naming -----


def test_naming_suggestion_is_stored_and_name_not_set_carries_it(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """With no extracted name, the suggestion waits on the field and NAME_NOT_SET shows it."""
    name_key = bundle.business_rules.record_name_field().key
    replies = replies_with_unresolved(bundle)
    # A record whose name extraction found nothing: build it from an empty-name reply
    reply = json.loads(str(replies["extraction"][0]))
    for record in reply["records"]:
        record["fields"][name_key] = {
            "status": "not_found",
            "value": None,
            "evidence": [],
            "alternatives": [],
            "warning": None,
        }
    replies["extraction"] = [json.dumps(reply)]
    run = process_run(tmp_path, bundle, synthetic_documents, replies)
    [issue, *_] = run.issues_with_code("NAME_NOT_SET")
    assert issue.details["suggestion"]["value"] == "Syn Name One"  # type: ignore[index]
    record = run.database.read_records(RUN_ID)[0]
    assert record.fields[name_key].output.value is None


def test_naming_drops_names_that_fail_the_code_checks(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """A name that is too long, or repeats another suggestion, is not offered."""
    name_rule = bundle.business_rules.record_name_field()
    assert name_rule.max_length is not None
    too_long = "x" * (name_rule.max_length + 1)
    replies = replies_with_unresolved(bundle)
    replies["naming"] = [naming_reply([("rec_0001", too_long), ("rec_0002", "Syn Same")])]
    run = process_run(tmp_path, bundle, synthetic_documents, replies)
    first, second = run.database.read_records(RUN_ID)
    assert first.fields[name_rule.key].suggestion is None
    assert second.fields[name_rule.key].suggestion is not None
    # The same name twice: only the first is kept
    replies["naming"] = [naming_reply([("rec_0001", "Syn Same"), ("rec_0002", "syn same")])]
    run = process_run(tmp_path / "again", bundle, synthetic_documents, replies)
    first, second = run.database.read_records(RUN_ID)
    assert first.fields[name_rule.key].suggestion is not None
    assert second.fields[name_rule.key].suggestion is None


# ----- Caches -----


def test_cache_hit_skips_the_calls_and_a_miss_makes_them(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """A second run with the same values and versions makes no Matching or Naming call."""
    replies = replies_with_unresolved(bundle)
    replies["matching"] = [matching_reply([("m_0001", None)])]
    caches = make_memory_caches()
    first = process_run(tmp_path / "one", bundle, synthetic_documents, replies, step_caches=caches)
    assert len(first.client.calls_for("matching")) == 1
    assert len(first.client.calls_for("naming")) == 1
    second = process_run(tmp_path / "two", bundle, synthetic_documents, replies, step_caches=caches)
    assert second.client.calls_for("matching") == []
    assert second.client.calls_for("naming") == []
    # Different caches (a miss) call again
    third = process_run(tmp_path / "three", bundle, synthetic_documents, replies)
    assert len(third.client.calls_for("naming")) == 1


# ----- Plausibility -----


def rules_with_active_check(business_rules: BusinessRules) -> tuple[BusinessRules, str]:
    """Return the rules with their first [Plausibility] check made active, and its ID."""
    check = next(rule for rule in business_rules.business.rules if rule.step == "Plausibility")
    active = check.model_copy(update={"status": "Design"})
    rules = [
        active if rule.rule_id == check.rule_id else rule for rule in business_rules.business.rules
    ]
    business = business_rules.business.model_copy(update={"rules": rules})
    return business_rules.model_copy(update={"business": business}), check.rule_id


def test_plausibility_is_not_called_without_an_active_check(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """The shipped config has no active [Plausibility] check, so there is no call or warning."""
    run = process_run(tmp_path, bundle, synthetic_documents, replies_with_unresolved(bundle))
    assert run.client.calls_for("plausibility") == []
    assert "PLAUSIBILITY_SKIPPED" not in issue_codes(run)


def test_plausibility_finding_is_a_warning_and_unknown_check_ids_are_dropped(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """A finding under an active check is a PLAUSIBILITY_CHECK on its first field; others drop."""
    rules, check_id = rules_with_active_check(bundle.business_rules)
    name_key = rules.record_name_field().key
    replies = replies_with_unresolved(bundle)
    replies["plausibility"] = [
        plausibility_reply(
            [("rec_0001", check_id, [name_key]), ("rec_0002", "SYN-UNKNOWN", [name_key])]
        )
    ]
    run = process_run(tmp_path, bundle, synthetic_documents, replies, business_rules=rules)
    [issue] = run.issues_with_code("PLAUSIBILITY_CHECK")
    assert (issue.record_id, issue.field, issue.severity) == ("rec_0001", name_key, "warning")
    assert issue.details == {"check_id": check_id}
    assert check_id in issue.message


def test_plausibility_blank_model_skips_with_a_warning(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """A blank PLAUSIBILITY_MODEL skips the review and adds PLAUSIBILITY_SKIPPED."""
    rules, _ = rules_with_active_check(bundle.business_rules)
    replies = replies_with_unresolved(bundle)
    run = process_run(
        tmp_path,
        bundle,
        synthetic_documents,
        replies,
        client=blank_client(replies, "plausibility"),
        business_rules=rules,
    )
    assert run.client.calls_for("plausibility") == []
    assert "PLAUSIBILITY_SKIPPED" in issue_codes(run)
    assert run.database.read_run(RUN_ID).status == "in_review"


# ----- State -----


def test_the_checkpointed_state_holds_no_document_text(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """After every node ran, the saved state has records and references, not chunk text."""
    run = process_run(tmp_path, bundle, synthetic_documents, replies_with_unresolved(bundle))
    with open_checkpointer(run.checkpoint_path) as checkpointer:
        saved = checkpointer.get_tuple({"configurable": {"thread_id": RUN_ID}})
    assert saved is not None
    state_text = json.dumps(saved.checkpoint["channel_values"], default=str)
    # This sentence is in the synthetic Word method but is not part of any record's evidence
    assert "Synthetic handling notes for the made-up procedure." not in state_text
    assert "chunk_ids" in state_text
