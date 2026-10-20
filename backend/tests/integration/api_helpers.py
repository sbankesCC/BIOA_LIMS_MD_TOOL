"""Shared helpers for API tests: an app on temporary stores with the fake LLM and a waitable runner.

Settings are passed in directly (no `.env`); every document is synthetic.
"""

from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from fastapi.testclient import TestClient

from app.api.dependencies import get_llm_client_factory, get_task_runner
from app.config.bundle import ConfigBundle
from app.llm.fake_client import FakeLLMClient, FakeReply
from app.main import create_app
from app.runs.background import ThreadTaskRunner
from app.settings import Settings
from tests.conftest import CLIENT_CONFIG_DIR
from tests.fixtures.fake_llm import extraction_reply, verification_reply

USER = "synthetic.user"
CHANGE_TIME = "2026-10-20T12:00:00Z"
WAIT_SECONDS = 120.0

# Two records (synthetic table rows 1 and 2) and a verification with nothing to report
TWO_ROWS = (("R1", 1), ("R2", 2))

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ApiResponse(Protocol):
    """What the tests read from a test client response."""

    @property
    def status_code(self) -> int:
        """Return the HTTP status."""
        ...

    @property
    def text(self) -> str:
        """Return the body as text."""
        ...

    def json(self) -> Any:
        """Return the parsed JSON body."""
        ...


@dataclass
class ApiHarness:
    """A test client on an app with temporary stores, and the runner that processes runs."""

    client: TestClient
    runner: ThreadTaskRunner

    def start_run(
        self, files: Sequence[tuple[str, bytes]], name: str = "synthetic run"
    ) -> ApiResponse:
        """Upload files as a new run and wait until its processing has finished."""
        upload = [("files", (file_name, content, DOCX_TYPE)) for file_name, content in files]
        response = self.client.post("/runs", files=upload, data={"name": name})
        self.runner.wait_for_all(WAIT_SECONDS)
        return response

    def post_changes(self, run_id: str, changes: list[dict[str, Any]]) -> ApiResponse:
        """Send a changes request (CONTRACTS §6)."""
        body = {"user": "sent by the UI", "timestamp": CHANGE_TIME, "changes": changes}
        return self.client.post(f"/runs/{run_id}/changes", json=body)


def happy_replies(bundle: ConfigBundle) -> dict[str, list[FakeReply]]:
    """Return fake replies for a clean run: two records, nothing to report."""
    return {
        "extraction": [extraction_reply(bundle.field_rules, TWO_ROWS)],
        "extraction_verification": [verification_reply()],
    }


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    """Return settings on temporary stores with a signed-in admin user; overrides win."""
    values: dict[str, object] = {
        "client_config_dir": str(CLIENT_CONFIG_DIR),
        "storage_dir": str(tmp_path / "storage"),
        "review_db": str(tmp_path / "review.sqlite"),
        "checkpoint_db": str(tmp_path / "checkpoints.sqlite"),
        "llm_retries": 0,
        "pilot_user": USER,
        "pilot_user_roles": "user,admin",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # pyright: ignore[reportCallIssue]


@contextmanager
def open_api(
    settings: Settings, replies: Mapping[str, Sequence[FakeReply]] | None = None
) -> Generator[ApiHarness]:
    """Start the app with a fresh fake LLM client per use and a runner the test can wait on."""
    app = create_app(settings)
    runner = ThreadTaskRunner()
    fake_replies = dict(replies or {})
    app.dependency_overrides[get_llm_client_factory] = lambda: lambda: FakeLLMClient(fake_replies)
    app.dependency_overrides[get_task_runner] = lambda: runner
    try:
        with TestClient(app) as client:
            yield ApiHarness(client, runner)
    finally:
        runner.wait_for_all(WAIT_SECONDS)
        runner.shutdown()


def read_file(documents: Mapping[str, Path], file_name: str) -> tuple[str, bytes]:
    """Return a synthetic document as an upload (name, contents)."""
    return file_name, documents[file_name].read_bytes()


def assert_error(response: ApiResponse, status: int, code: str) -> dict[str, Any]:
    """Check a response has the error shape with this status and code; return the error."""
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    return body["error"]
