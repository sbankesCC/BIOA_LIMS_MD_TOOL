"""LLM client interface: one request (text and image parts plus a JSON schema) in, one response out.

Agents reach the LLM only through `LLMClient`; `OpenAIClient` and `FakeLLMClient` implement it.
Calls go through `tracing.TracedCaller`, which retries and writes a trace for every call.
"""

from typing import Annotated, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.trace import LlmNode


class TextPart(BaseModel):
    """A piece of prompt text."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["text"] = "text"
    text: str


class ImagePart(BaseModel):
    """A scanned page image, by its run store reference (never the image bytes)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["image"] = "image"
    chunk_id: str
    image_ref: str


PromptPart = Annotated[TextPart | ImagePart, Field(discriminator="type")]


class LLMRequest(BaseModel):
    """One LLM call: who asks (run, node), the prompt parts and the strict JSON schema."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    node: LlmNode
    prompt_template: str
    prompt_version: str
    parts: list[PromptPart]
    schema_name: str
    json_schema: dict[str, Any]


class LLMResponse(BaseModel):
    """What the LLM returned: its text, the model, token counts and whether it was cut off."""

    model_config = ConfigDict(extra="forbid")

    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    is_truncated: bool = False


class LLMCallError(Exception):
    """An LLM call failed; `is_retryable` is True for timeouts, rate limits and server errors."""

    def __init__(self, message: str, is_retryable: bool) -> None:
        """Keep a plain message (no prompt or document text) and whether a retry may help."""
        super().__init__(message)
        self.is_retryable = is_retryable


class LLMClient(Protocol):
    """Sends one request to an LLM provider and returns its response."""

    @property
    def provider(self) -> str:
        """Return the provider name written to traces (e.g. `openai`, `fake`)."""
        ...

    def model_for(self, node: LlmNode) -> str:
        """Return the model used for a node; raise MissingSettingError if it is not set."""
        ...

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Send the request; raise LLMCallError when the call fails."""
        ...
