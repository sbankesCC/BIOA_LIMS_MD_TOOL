"""App startup tests: starts with every setting blank, loads config, refuses broken config."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config.errors import ConfigError
from app.main import create_app
from app.settings import load_settings
from tests.conftest import CLIENT_CONFIG_DIR, edit_yaml


@pytest.mark.usefixtures("blank_environment")
def test_app_starts_with_every_setting_blank() -> None:
    """With nothing set, the app starts and /health says which setting loads the config."""
    with TestClient(create_app(load_settings(env_file=None))) as client:
        response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["config_versions"] is None
    assert "CLIENT_CONFIG_DIR" in body["message"]


@pytest.mark.usefixtures("blank_environment")
def test_health_reports_config_versions(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the client config set, /health reports the version of each config file."""
    monkeypatch.setenv("CLIENT_CONFIG_DIR", str(CLIENT_CONFIG_DIR))
    with TestClient(create_app(load_settings(env_file=None))) as client:
        body = client.get("/health").json()
    versions = body["config_versions"]
    assert set(versions) == {
        "field_rules",
        "issue_catalogue",
        "lookup_lists",
        "dfd_template",
        "reference_data_mapping",
        "prompts",
    }
    assert body["message"] is None


@pytest.mark.usefixtures("blank_environment")
def test_broken_config_stops_startup(monkeypatch: pytest.MonkeyPatch, config_copy: Path) -> None:
    """A broken config stops the app at startup with a message naming the problem."""
    edit_yaml(config_copy / "field_rules.yaml", lambda data: data.pop("version"))
    monkeypatch.setenv("CLIENT_CONFIG_DIR", str(config_copy))
    app = create_app(load_settings(env_file=None))
    with pytest.raises(ConfigError, match="field_rules.yaml: version"):
        with TestClient(app):
            pass
