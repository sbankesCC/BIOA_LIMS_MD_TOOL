"""LLM layer tests: token estimate, fake client, tracing and retries, OpenAI client settings.

No test calls the network. The OpenAI smoke test runs only when asked for (RUN_OPENAI_SMOKE=1)
and its settings are set in the environment.
"""

import json
import os
from pathlib import Path

import openai
import pytest

from app.agents.duplicate_judge import UNANSWERED_REASON, DuplicateJudgeAgent
from app.agents.extraction import find_record_id_problems
from app.config.bundle import ConfigBundle
from app.contracts.extraction import ExtractionOutput
from app.contracts.reference import ReferenceType
from app.llm.client import LLMCallError, LLMRequest, LLMResponse, TextPart
from app.llm.fake_client import FakeLLMClient, load_fake_replies
from app.llm.openai_client import OpenAIClient
from app.llm.provider import LLMProviderError, make_llm_client
from app.llm.token_estimate import (
    estimate_image_tokens,
    estimate_parts_tokens,
    estimate_text_tokens,
)
from app.llm.tracing import TracedCaller, read_traces
from app.llm_schema import build_judge_schema
from app.settings import MissingSettingError, Settings, load_settings
from app.storage.run_store import RunFolder, RunStore
from app.validation.judge_cache import JudgeRequest
from tests.fixtures.fake_llm import extraction_reply

RUN_ID = "run_0001"


def make_folder(tmp_path: Path) -> RunFolder:
    """Return a new synthetic run folder."""
    return RunStore(tmp_path / "storage").create_run(RUN_ID)


def make_request(text: str = "synthetic prompt") -> LLMRequest:
    """Return a small synthetic judge request."""
    return LLMRequest(
        run_id=RUN_ID,
        node="duplicate_judge",
        prompt_template="duplicate_judge",
        prompt_version="0.1",
        parts=[TextPart(text=text)],
        schema_name="judge_output",
        json_schema=build_judge_schema(),
    )


def always_fine(response: LLMResponse) -> str | None:
    """Accept every response."""
    return None


# ----- Token estimate -----


def test_text_tokens_are_characters_over_three_and_a_half() -> None:
    """Text is estimated at 3.5 characters per token, rounded up."""
    assert estimate_text_tokens("x" * 35) == 10
    assert estimate_text_tokens("x" * 36) == 11


def test_image_tokens_follow_the_tile_formula() -> None:
    """A square page is scaled to 768 per side (4 tiles); a tall page fits 2048 first."""
    assert estimate_image_tokens(1024, 1024) == 85 + 170 * 4
    assert estimate_image_tokens(2048, 4096) == 85 + 170 * 6
    assert estimate_image_tokens(100, 100) == 85 + 170


def test_parts_estimate_adds_text_images_and_schema() -> None:
    """The estimate counts every part plus the schema text."""
    parts = make_request("x" * 35).parts
    assert estimate_parts_tokens(parts, lambda ref: (1, 1), "y" * 7) == 12


# ----- Fake client -----


def test_fake_client_answers_by_node_and_attempt() -> None:
    """The Nth call for a node gets the Nth reply; later calls repeat the last one."""
    client = FakeLLMClient({"duplicate_judge": ["first", "second"]})
    texts = [client.complete(make_request()).text for _ in range(3)]
    assert texts == ["first", "second", "second"]


def test_fake_client_without_a_reply_fails_plainly() -> None:
    """A node with no fixture raises a non-retryable error naming the node."""
    with pytest.raises(LLMCallError, match="duplicate_judge"):
        FakeLLMClient({}).complete(make_request())


def test_fake_replies_load_from_a_folder(tmp_path: Path) -> None:
    """Fixture files `<node>.<attempt>.json` load in attempt order."""
    (tmp_path / "extraction.2.json").write_text("second", encoding="utf-8")
    (tmp_path / "extraction.1.json").write_text("first", encoding="utf-8")
    (tmp_path / "notes.md").write_text("synthetic", encoding="utf-8")
    assert load_fake_replies(tmp_path) == {"extraction": ["first", "second"]}


# ----- Tracing -----


def test_every_call_writes_a_trace_and_its_files(tmp_path: Path) -> None:
    """A call writes the trace record, request and response files in the run's llm folder."""
    folder = make_folder(tmp_path)
    client = FakeLLMClient({"duplicate_judge": [LLMResponse(text="{}", model="m", input_tokens=5)]})
    caller = TracedCaller(client, folder, {"field_rules": "0.3"}, retries=0)
    result = caller.call(make_request(), 1, always_fine)
    [trace] = read_traces(folder)
    assert (trace.trace_id, trace.status, trace.input_tokens) == (result.trace_id, "ok", 5)
    assert trace.config_versions == {"field_rules": "0.3"}
    assert trace.request_file == f"runs/{RUN_ID}/llm/llm_0001_request.json"
    request_file = json.loads((folder.llm_dir / "llm_0001_request.json").read_text("utf-8"))
    assert request_file["parts"][0]["text"] == "synthetic prompt"
    assert (folder.llm_dir / "llm_0001_response.json").is_file()


def test_retryable_errors_are_retried_and_traced(tmp_path: Path) -> None:
    """A timeout is retried up to LLM_RETRIES; each try has a trace (retry, then ok)."""
    folder = make_folder(tmp_path)
    timeout = LLMCallError("synthetic timeout", is_retryable=True)
    client = FakeLLMClient({"duplicate_judge": [timeout, "{}"]})
    TracedCaller(client, folder, {}, retries=1).call(make_request(), 1, always_fine)
    assert [trace.status for trace in read_traces(folder)] == ["retry", "ok"]


def test_retries_run_out_with_an_error_trace(tmp_path: Path) -> None:
    """When the tries run out the error is raised and the last trace is an error."""
    folder = make_folder(tmp_path)
    timeout = LLMCallError("synthetic timeout", is_retryable=True)
    caller = TracedCaller(FakeLLMClient({"duplicate_judge": [timeout]}), folder, {}, retries=1)
    with pytest.raises(LLMCallError):
        caller.call(make_request(), 1, always_fine)
    assert [trace.status for trace in read_traces(folder)] == ["retry", "error"]


def test_failed_check_is_a_schema_violation_trace(tmp_path: Path) -> None:
    """A response the check refuses is traced as a schema violation with the problem."""
    folder = make_folder(tmp_path)
    caller = TracedCaller(FakeLLMClient({"duplicate_judge": ["{}"]}), folder, {}, retries=0)
    result = caller.call(make_request(), 1, lambda response: "- synthetic problem")
    [trace] = read_traces(folder)
    assert (trace.status, trace.error_message) == ("schema_violation", "- synthetic problem")
    assert result.problem == "- synthetic problem"


def test_trace_ids_continue_after_existing_traces(tmp_path: Path) -> None:
    """A new caller for the same run continues the llm_ numbering."""
    folder = make_folder(tmp_path)
    client = FakeLLMClient({"duplicate_judge": ["{}"]})
    TracedCaller(client, folder, {}, retries=0).call(make_request(), 1, always_fine)
    second = TracedCaller(client, folder, {}, retries=0).call(make_request(), 1, always_fine)
    assert second.trace_id == "llm_0002"


# ----- Agents -----


def test_judge_that_cannot_answer_gives_unsure(tmp_path: Path, bundle: ConfigBundle) -> None:
    """Two bad judge responses make every candidate "unsure", so the user checks it."""
    folder = make_folder(tmp_path)
    client = FakeLLMClient({"duplicate_judge": ['{"judgments": []}']})
    caller = TracedCaller(client, folder, {}, retries=0)
    agent = DuplicateJudgeAgent(
        caller, RUN_ID, bundle.prompts["duplicate_judge"], bundle.field_rules
    )
    candidate = ReferenceType(candidate_id="ref_0001", name="Syn A2", version="1")
    output = agent.judge(JudgeRequest(record_id="rec_0001", values={}, candidates=[candidate]))
    assert [(j.candidate_id, j.verdict, j.reason) for j in output.judgments] == [
        ("ref_0001", "unsure", UNANSWERED_REASON)
    ]
    assert len(client.requests) == 2


def test_record_id_not_given_for_reextraction_is_a_problem(bundle: ConfigBundle) -> None:
    """The LLM may echo only the record IDs it was asked to re-extract."""
    output = ExtractionOutput.model_validate_json(
        extraction_reply(bundle.field_rules, [("rec_0001", 1), ("rec_0009", 2), ("R1", 3)])
    )
    problems = find_record_id_problems(output, frozenset({"rec_0001"}))
    assert problems == ["record_ref rec_0009 is not a record_id given in the problems to fix."]


# ----- OpenAI client -----


@pytest.mark.usefixtures("blank_environment")
def test_openai_client_names_a_missing_api_key(tmp_path: Path) -> None:
    """With OPENAI_API_KEY blank, building the client raises a plain MissingSettingError."""
    with pytest.raises(MissingSettingError, match="Set OPENAI_API_KEY in .env"):
        OpenAIClient(load_settings(env_file=None), tmp_path)


@pytest.mark.usefixtures("blank_environment")
def test_openai_client_names_a_missing_model(tmp_path: Path) -> None:
    """With a key but no model, the node's model setting is named (no network call)."""
    client = OpenAIClient(Settings(openai_api_key="synthetic-key"), tmp_path)
    with pytest.raises(MissingSettingError, match="Set VERIFICATION_MODEL in .env"):
        client.model_for("extraction_verification")


@pytest.mark.usefixtures("blank_environment")
def test_openai_client_uses_the_base_url_setting(tmp_path: Path) -> None:
    """OPENAI_BASE_URL (e.g. an Azure OpenAI v1 endpoint) becomes the SDK's base URL."""
    base_url = "https://synthetic.openai.azure.com/openai/v1/"
    settings = Settings(openai_api_key="synthetic-key", openai_base_url=base_url)
    client = OpenAIClient(settings, tmp_path)
    assert str(client.sdk.base_url) == base_url


@pytest.mark.usefixtures("blank_environment")
def test_blank_base_url_keeps_the_openai_default(tmp_path: Path) -> None:
    """With OPENAI_BASE_URL blank, the SDK keeps OpenAI's default address."""
    client = OpenAIClient(Settings(openai_api_key="synthetic-key"), tmp_path)
    assert str(client.sdk.base_url) == str(openai.OpenAI(api_key="synthetic-key").base_url)


@pytest.mark.usefixtures("blank_environment")
def test_provider_setting_is_required_and_checked(tmp_path: Path) -> None:
    """A blank LLM_PROVIDER is named; an unknown one gets a plain error."""
    with pytest.raises(MissingSettingError, match="LLM_PROVIDER"):
        make_llm_client(load_settings(env_file=None), tmp_path)
    with pytest.raises(LLMProviderError, match="openai"):
        make_llm_client(Settings(llm_provider="synthetic"), tmp_path)


@pytest.mark.skipif(
    os.environ.get("RUN_OPENAI_SMOKE") != "1"
    or not os.environ.get("OPENAI_API_KEY")
    or not os.environ.get("DUPLICATE_JUDGE_MODEL"),
    reason="Manual smoke test: set RUN_OPENAI_SMOKE=1, OPENAI_API_KEY and DUPLICATE_JUDGE_MODEL.",
)
def test_openai_smoke_judge_call(tmp_path: Path) -> None:
    """Manual: one small strict-schema judge call to the real API returns parseable JSON."""
    client = OpenAIClient(load_settings(env_file=None), tmp_path)
    prompt = (
        'Return {"judgments": [{"candidate_id": "ref_0001", "verdict": "unsure", '
        '"reason": "synthetic smoke test"}]}'
    )
    response = client.complete(make_request(prompt))
    assert "judgments" in json.loads(response.text)
