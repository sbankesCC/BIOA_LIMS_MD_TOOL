"""LLM provider choice: LLM_PROVIDER picks the client the app uses.

`openai` gives the OpenAI client. `fake` (local development only) answers from the fake reply
files in FAKE_LLM_REPLIES_DIR, which is read only when LLM_PROVIDER is `fake`.
"""

from pathlib import Path

from app.llm.client import LLMClient
from app.llm.fake_client import FAKE_PROVIDER, FakeLLMClient, load_fake_replies
from app.llm.openai_client import OPENAI_PROVIDER, OpenAIClient
from app.settings import Settings

FAKE_REPLIES_SETTING = "FAKE_LLM_REPLIES_DIR"


class LLMProviderError(Exception):
    """Raised when LLM_PROVIDER names a provider the app cannot build from settings."""


def make_llm_client(settings: Settings, storage_dir: Path) -> LLMClient:
    """Return the client LLM_PROVIDER names; a blank LLM_PROVIDER raises MissingSettingError."""
    provider = settings.require_text("LLM_PROVIDER").strip().lower()
    if provider == OPENAI_PROVIDER:
        return OpenAIClient(settings, storage_dir)
    if provider == FAKE_PROVIDER:
        return make_fake_client(settings)
    raise LLMProviderError(
        f"LLM_PROVIDER is '{provider}', which the app cannot use. Set it to {OPENAI_PROVIDER} "
        f"(or {FAKE_PROVIDER} for local development) in .env, then restart the app."
    )


def make_fake_client(settings: Settings) -> FakeLLMClient:
    """Return a fresh fake client on the reply files in FAKE_LLM_REPLIES_DIR (development only)."""
    folder = settings.require_path(FAKE_REPLIES_SETTING)
    # The folder must exist and hold `<node>.<attempt>.json` files; nothing is made up
    if not folder.is_dir():
        raise LLMProviderError(
            f"{FAKE_REPLIES_SETTING} is not a folder. Set it to a folder of fake replies "
            "(such as evals/cases/synthetic_001/fake_llm) in .env, then restart the app."
        )
    replies = load_fake_replies(folder)
    if not replies:
        raise LLMProviderError(
            f"{FAKE_REPLIES_SETTING} has no fake reply files (<node>.<attempt>.json). Point it "
            "at a folder that has them in .env, then restart the app."
        )
    return FakeLLMClient(replies)
