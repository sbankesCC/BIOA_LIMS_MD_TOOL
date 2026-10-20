"""Fake LLM client: returns prepared replies by node and attempt, so tests and evals never call out.

Replies are synthetic fixtures. The Nth call for a node gets that node's Nth reply; calls past
the last reply get the last one again. A reply can be text, a full response, or an error to raise.
"""

import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from app.contracts.trace import LlmNode
from app.llm.client import LLMCallError, LLMRequest, LLMResponse

FAKE_PROVIDER = "fake"
FAKE_MODEL = "fake-model"

# Fixture files in a folder are named `<node>.<attempt>.json`, e.g. `extraction.1.json`
FIXTURE_FILE_PATTERN = re.compile(r"^(?P<node>[a-z_]+)\.(?P<attempt>\d+)\.json$")

FakeReply = str | LLMResponse | LLMCallError


class FakeLLMClient:
    """An LLM client that answers from fixtures and remembers every request it got."""

    def __init__(self, replies: Mapping[str, Sequence[FakeReply]], model: str = FAKE_MODEL) -> None:
        """Keep the replies per node name; `model` is reported for every node."""
        self.replies = {node: list(node_replies) for node, node_replies in replies.items()}
        self.model = model
        self.requests: list[LLMRequest] = []

    @property
    def provider(self) -> str:
        """Return the provider name written to traces."""
        return FAKE_PROVIDER

    def model_for(self, node: LlmNode) -> str:
        """Return the fake model name (the same for every node)."""
        return self.model

    def calls_for(self, node: LlmNode) -> list[LLMRequest]:
        """Return the requests sent for one node, in order."""
        return [request for request in self.requests if request.node == node]

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Return the reply for this node and attempt, or raise the error stored there."""
        attempt_index = len(self.calls_for(request.node))
        self.requests.append(request)
        node_replies = self.replies.get(request.node, [])
        if not node_replies:
            raise LLMCallError(
                f"The fake LLM has no reply for node {request.node}. Add a fixture for it.",
                is_retryable=False,
            )
        # Calls past the last reply get the last one again
        reply = node_replies[min(attempt_index, len(node_replies) - 1)]
        if isinstance(reply, LLMCallError):
            raise reply
        if isinstance(reply, LLMResponse):
            return reply
        return LLMResponse(text=reply, model=self.model)


def load_fake_replies(folder: Path) -> dict[str, list[FakeReply]]:
    """Read fixture files named `<node>.<attempt>.json` from a folder, in attempt order."""
    found: dict[str, list[tuple[int, str]]] = {}
    for path in folder.iterdir():
        match = FIXTURE_FILE_PATTERN.match(path.name)
        if match is None:
            continue
        text = path.read_text(encoding="utf-8")
        found.setdefault(match["node"], []).append((int(match["attempt"]), text))
    # Attempts are sorted by number, so `extraction.2.json` answers the second call
    return {node: [text for _, text in sorted(items)] for node, items in found.items()}
