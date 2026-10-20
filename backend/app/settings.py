"""Deployment settings read from the environment (and `.env` at the repo root).

Every setting is optional so the app starts with all of them blank. A feature that needs a
setting with no usable blank meaning calls a `require_*` method, which names the setting.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# The repo root: relative paths in settings are resolved against it, whatever the working directory
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


class MissingSettingError(Exception):
    """Raised when a feature needs a setting that is blank."""

    def __init__(self, name: str) -> None:
        """Build a plain message that names the blank setting and says how to fix it."""
        self.name = name
        super().__init__(f"Set {name} in .env, then restart the app.")


class Settings(BaseSettings):
    """All deployment settings; blank values become None (see `env.example` for meanings)."""

    model_config = SettingsConfigDict(env_ignore_empty=True, extra="ignore")

    # Paths (relative paths are resolved against the repo root)
    client_config_dir: str | None = None
    storage_dir: str | None = None
    checkpoint_db: str | None = None
    review_db: str | None = None

    # LLM provider and models
    llm_provider: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    extraction_model: str | None = None
    verification_model: str | None = None
    duplicate_judge_model: str | None = None
    llm_retries: int | None = None

    # Limits: blank (None) means no limit
    max_file_size_mb: int | None = None
    max_files_per_run: int | None = None
    max_input_tokens: int | None = None
    max_duplicate_judge_calls: int | None = None

    # Re-extraction attempts; 1 is the documented default
    max_reextract: int = 1

    # LLM trace retention in days: blank (None) keeps everything
    llm_trace_retention_days: int | None = None

    # Placeholder sign-in
    pilot_user: str | None = None
    pilot_user_roles: str | None = None

    def require_text(self, name: str) -> str:
        """Return a text setting, or raise MissingSettingError if it is blank."""
        value = getattr(self, name.lower())
        if not isinstance(value, str) or not value.strip():
            raise MissingSettingError(name.upper())
        return value

    def require_integer(self, name: str) -> int:
        """Return a whole-number setting, or raise MissingSettingError if it is blank."""
        value = getattr(self, name.lower())
        if not isinstance(value, int):
            raise MissingSettingError(name.upper())
        return value

    def require_path(self, name: str) -> Path:
        """Return a path setting resolved against the repo root, or raise if it is blank."""
        return resolve_path(self.require_text(name))

    def require_roles(self) -> list[str]:
        """Return the pilot user's roles from the comma list in PILOT_USER_ROLES."""
        roles = [role.strip() for role in self.require_text("PILOT_USER_ROLES").split(",")]
        return [role for role in roles if role]


def resolve_path(value: str) -> Path:
    """Turn a path setting into an absolute path; relative paths start at the repo root."""
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def load_settings(env_file: Path | None = ENV_FILE) -> Settings:
    """Read settings from the environment, plus `env_file` when given and present."""
    return Settings(_env_file=env_file)  # pyright: ignore[reportCallIssue]
