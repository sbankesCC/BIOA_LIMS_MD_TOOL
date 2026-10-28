"""Tests for settings: blank meanings, required settings and the env.example listing."""

import re
from pathlib import Path

import pytest

from app.settings import PROJECT_ROOT, MissingSettingError, Settings, load_settings


@pytest.mark.usefixtures("blank_environment")
def test_every_setting_can_be_blank() -> None:
    """With nothing set, every setting is None except MAX_REEXTRACT's documented default."""
    settings = load_settings(env_file=None)
    values = settings.model_dump()
    assert values.pop("max_reextract") == 1
    assert all(value is None for value in values.values())


@pytest.mark.usefixtures("blank_environment")
def test_blank_string_counts_as_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty value in the environment means blank, also for number settings."""
    monkeypatch.setenv("MAX_FILE_SIZE_MB", "")
    monkeypatch.setenv("PILOT_USER", "")
    settings = load_settings(env_file=None)
    assert settings.max_file_size_mb is None
    assert settings.pilot_user is None


@pytest.mark.usefixtures("blank_environment")
def test_missing_required_setting_names_it() -> None:
    """A feature asking for a blank setting gets a message naming the setting."""
    settings = load_settings(env_file=None)
    with pytest.raises(MissingSettingError, match="Set PILOT_USER in .env"):
        settings.require_text("PILOT_USER")
    with pytest.raises(MissingSettingError, match="Set LLM_RETRIES in .env"):
        settings.require_integer("LLM_RETRIES")


@pytest.mark.usefixtures("blank_environment")
def test_set_values_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """Values from the environment are parsed into their types."""
    monkeypatch.setenv("MAX_INPUT_TOKENS", "5000")
    monkeypatch.setenv("PILOT_USER_ROLES", "user, admin")
    settings = load_settings(env_file=None)
    assert settings.require_integer("MAX_INPUT_TOKENS") == 5000
    assert settings.require_roles() == ["user", "admin"]


@pytest.mark.usefixtures("blank_environment")
def test_relative_paths_start_at_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """A relative path setting resolves against the repo root, whatever the working folder."""
    monkeypatch.setenv("STORAGE_DIR", "./data")
    settings = load_settings(env_file=None)
    assert settings.require_path("STORAGE_DIR") == PROJECT_ROOT / "data"


@pytest.mark.usefixtures("blank_environment")
def test_absolute_paths_are_kept(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """An absolute path setting is used as given."""
    monkeypatch.setenv("REVIEW_DB", str(tmp_path / "review.sqlite"))
    settings = load_settings(env_file=None)
    assert settings.require_path("REVIEW_DB") == tmp_path / "review.sqlite"


def test_env_example_lists_exactly_the_settings() -> None:
    """Every setting is in env.example, and env.example has no unknown settings."""
    text = (PROJECT_ROOT / "env.example").read_text(encoding="utf-8")
    listed = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", text, flags=re.MULTILINE))
    expected = {name.upper() for name in Settings.model_fields}
    assert listed == expected
