"""OpenAI client: sends a request through the Responses API with a strict structured-output schema.

Needs OPENAI_API_KEY and the model setting of each node (EXTRACTION_MODEL, VERIFICATION_MODEL,
DUPLICATE_JUDGE_MODEL); a blank one raises MissingSettingError naming it. The SDK's own retries
are off: `tracing.TracedCaller` retries (LLM_RETRIES), so every try is traced.
"""

import base64
from pathlib import Path

import openai
from openai.types.responses import (
    ResponseInputContentParam,
    ResponseInputParam,
    ResponseTextConfigParam,
)

from app.contracts.trace import LlmNode
from app.llm.client import ImagePart, LLMCallError, LLMRequest, LLMResponse, TextPart
from app.settings import Settings
from app.storage.run_store import resolve_inside

OPENAI_PROVIDER = "openai"

# The setting that names the model of each node
MODEL_SETTINGS: dict[LlmNode, str] = {
    "extraction": "EXTRACTION_MODEL",
    "extraction_verification": "VERIFICATION_MODEL",
    "duplicate_judge": "DUPLICATE_JUDGE_MODEL",
}

# Scanned pages are sent at high detail: values are read from them
IMAGE_DETAIL = "high"
IMAGE_MEDIA_TYPE = "image/png"

# Errors worth another try: timeouts, lost connections, rate limits and server errors
RETRYABLE_ERRORS = (openai.APIConnectionError, openai.RateLimitError, openai.InternalServerError)

# The reason the API gives when a response stopped at the output token limit
TRUNCATED_REASON = "max_output_tokens"


class OpenAIClient:
    """An LLM client for the OpenAI Responses API."""

    def __init__(self, settings: Settings, storage_dir: Path) -> None:
        """Check the API key is set and connect; page images are read from `storage_dir`."""
        api_key = settings.require_text("OPENAI_API_KEY")
        self.settings = settings
        self.storage_dir = storage_dir
        self.sdk = openai.OpenAI(api_key=api_key, max_retries=0)

    @property
    def provider(self) -> str:
        """Return the provider name written to traces."""
        return OPENAI_PROVIDER

    def model_for(self, node: LlmNode) -> str:
        """Return the node's model from its setting; raise MissingSettingError if blank."""
        return self.settings.require_text(MODEL_SETTINGS[node])

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Send the request as one user message with a strict JSON schema; map SDK errors."""
        model = self.model_for(request.node)
        text_format: ResponseTextConfigParam = {
            "format": {
                "type": "json_schema",
                "name": request.schema_name,
                "schema": request.json_schema,
                "strict": True,
            }
        }
        try:
            response = self.sdk.responses.create(
                model=model, input=self.build_input(request), text=text_format, store=False
            )
        except RETRYABLE_ERRORS as error:
            raise LLMCallError(describe_error(error), is_retryable=True) from error
        except openai.OpenAIError as error:
            raise LLMCallError(describe_error(error), is_retryable=False) from error
        # Token counts and the cut-off flag come from the response metadata
        usage = response.usage
        details = response.incomplete_details
        return LLMResponse(
            text=response.output_text,
            model=response.model or model,
            input_tokens=usage.input_tokens if usage is not None else 0,
            output_tokens=usage.output_tokens if usage is not None else 0,
            is_truncated=details is not None and details.reason == TRUNCATED_REASON,
        )

    def build_input(self, request: LLMRequest) -> ResponseInputParam:
        """Build one user message holding every text and image part, in order."""
        content: list[ResponseInputContentParam] = []
        for part in request.parts:
            if isinstance(part, TextPart):
                content.append({"type": "input_text", "text": part.text})
            else:
                content.append(self.build_image(part))
        return [{"role": "user", "content": content}]

    def build_image(self, part: ImagePart) -> ResponseInputContentParam:
        """Read a page image from the run store and send it as a base64 data URL."""
        image_bytes = resolve_inside(self.storage_dir, part.image_ref).read_bytes()
        encoded = base64.b64encode(image_bytes).decode("ascii")
        return {
            "type": "input_image",
            "image_url": f"data:{IMAGE_MEDIA_TYPE};base64,{encoded}",
            "detail": IMAGE_DETAIL,
        }


def describe_error(error: openai.OpenAIError) -> str:
    """Return a plain message naming the error kind (and HTTP status), never request content."""
    status = getattr(error, "status_code", None)
    status_text = f" (HTTP {status})" if isinstance(status, int) else ""
    return (
        f"The OpenAI call failed: {type(error).__name__}{status_text}. "
        "Check OPENAI_API_KEY, the model settings and the network, then retry the run."
    )
