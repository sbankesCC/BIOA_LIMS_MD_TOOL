"""API tests for the dev-only fake LLM provider (LLM_PROVIDER=fake, FAKE_LLM_REPLIES_DIR).

The app builds its own client from settings (no test override of the client factory). The
eval case `synthetic_001` gives the synthetic documents and their fake replies.
"""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_task_runner
from app.main import create_app
from app.runs.background import ThreadTaskRunner
from app.settings import PROJECT_ROOT, Settings
from tests.fixtures.make_documents import WORD_FILE
from tests.integration.api_helpers import (
    DOCX_TYPE,
    WAIT_SECONDS,
    ApiHarness,
    assert_error,
    make_settings,
    read_file,
)

CASE_FOLDER = PROJECT_ROOT / "evals" / "cases" / "synthetic_001"
REPLIES_FOLDER = CASE_FOLDER / "fake_llm"
DOCUMENTS_FOLDER = CASE_FOLDER / "documents"

pytestmark = pytest.mark.usefixtures("blank_environment")


@contextmanager
def open_app(settings: Settings) -> Generator[ApiHarness]:
    """Start the app with its own LLM client from settings and a runner the test can wait on."""
    app = create_app(settings)
    runner = ThreadTaskRunner()
    app.dependency_overrides[get_task_runner] = lambda: runner
    try:
        with TestClient(app) as client:
            yield ApiHarness(client, runner)
    finally:
        runner.wait_for_all(WAIT_SECONDS)
        runner.shutdown()


def read_case_documents() -> list[tuple[str, bytes]]:
    """Return the case's documents in name order, the order its fake replies expect."""
    paths = sorted(DOCUMENTS_FOLDER.iterdir(), key=lambda path: path.name)
    return [(path.name, path.read_bytes()) for path in paths]


def fake_settings(tmp_path: Path) -> Settings:
    """Return settings with the fake provider on the case's replies (no model settings)."""
    return make_settings(tmp_path, llm_provider="fake", fake_llm_replies_dir=str(REPLIES_FOLDER))


def test_fake_provider_takes_the_synthetic_case_to_review(tmp_path: Path) -> None:
    """The case's documents with LLM_PROVIDER=fake reach review with the fake model names."""
    with open_app(fake_settings(tmp_path)) as api:
        started = api.start_run(read_case_documents())
        assert started.status_code == 202, started.text
        run = api.client.get(f"/runs/{started.json()['run_id']}").json()
        assert run["status"] == "in_review"
        assert set(run["models"].values()) == {"fake-model"}
        assert run["counts"]["records"] > 0
        view = api.client.get(f"/runs/{run['run_id']}/records").json()
        assert len(view["rows"]) == run["counts"]["records"]


def test_fake_provider_fails_documents_its_replies_do_not_match(
    tmp_path: Path, synthetic_documents: dict[str, Path]
) -> None:
    """Other documents fail the run plainly: the replies cite chunks they do not have."""
    with open_app(fake_settings(tmp_path)) as api:
        started = api.start_run([read_file(synthetic_documents, WORD_FILE)])
        run_id = started.json()["run_id"]
        run = api.client.get(f"/runs/{run_id}").json()
        assert run["status"] == "failed"
        assert run["counts"]["records"] == 0
        summary = next(s for s in api.client.get("/runs").json() if s["run_id"] == run_id)
        assert summary["failure_reason"]


def test_openai_provider_does_not_use_the_fake_replies(tmp_path: Path) -> None:
    """With LLM_PROVIDER=openai and no key, a run start names the key; nothing is stored."""
    settings = make_settings(
        tmp_path, llm_provider="openai", fake_llm_replies_dir=str(REPLIES_FOLDER)
    )
    with open_app(settings) as api:
        upload = [("files", (name, content, DOCX_TYPE)) for name, content in read_case_documents()]
        response = api.client.post("/runs", files=upload, data={"name": "synthetic run"})
        error = assert_error(response, 503, "SETTING_MISSING")
        assert error["details"]["setting"] == "OPENAI_API_KEY"
        assert api.client.get("/runs").json() == []
