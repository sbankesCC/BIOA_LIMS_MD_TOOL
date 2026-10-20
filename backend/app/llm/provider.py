"""LLM provider choice: LLM_PROVIDER picks the client the app uses.

`openai` gives the OpenAI client. The fake provider needs fixtures, so tests and evals build a
`FakeLLMClient` themselves and pass it in; the app cannot make one from settings alone.
"""

from pathlib import Path

from app.llm.client import LLMClient
from app.llm.openai_client import OPENAI_PROVIDER, OpenAIClient
from app.settings import Settings


class LLMProviderError(Exception):
    """Raised when LLM_PROVIDER names a provider the app cannot build from settings."""


def make_llm_client(settings: Settings, storage_dir: Path) -> LLMClient:
    """Return the client LLM_PROVIDER names; a blank LLM_PROVIDER raises MissingSettingError."""
    provider = settings.require_text("LLM_PROVIDER").strip().lower()
    if provider == OPENAI_PROVIDER:
        return OpenAIClient(settings, storage_dir)
    raise LLMProviderError(
        f"LLM_PROVIDER is '{provider}', which the app cannot use. Set it to {OPENAI_PROVIDER} "
        "in .env, then restart the app (the fake provider is only for tests and evals)."
    )
