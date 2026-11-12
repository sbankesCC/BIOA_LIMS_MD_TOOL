"""Shared test fixtures: client config, editable copies, blank environment, synthetic documents."""

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.config.bundle import ConfigBundle, load_config_bundle
from app.config.errors import ConfigError
from app.settings import PROJECT_ROOT, Settings
from tests.fixtures.make_documents import make_all_documents

CLIENT_CONFIG_DIR = PROJECT_ROOT / "clients" / "bioa"
SOURCE_WORKBOOK = CLIENT_CONFIG_DIR / "source" / "BAL_Consumable_Type_Definitions.xlsx"


@pytest.fixture(scope="session")
def bundle() -> ConfigBundle:
    """Load the real client config once for the whole test session."""
    return load_config_bundle(CLIENT_CONFIG_DIR)


@pytest.fixture(scope="session")
def synthetic_documents(
    tmp_path_factory: pytest.TempPathFactory, bundle: ConfigBundle
) -> dict[str, Path]:
    """Generate the synthetic test documents once, into a temp folder, by file name."""
    folder = tmp_path_factory.mktemp("synthetic_documents")
    return make_all_documents(folder, bundle.dfd_template.headers)


@pytest.fixture
def config_copy(tmp_path: Path) -> Path:
    """Copy the client config to a temp folder so a test can break it."""
    target = tmp_path / "config"
    shutil.copytree(CLIENT_CONFIG_DIR, target, ignore=shutil.ignore_patterns("source"))
    return target


@pytest.fixture
def blank_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every app setting from the environment, so all of them are blank."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


def assert_config_error(config_dir: Path, expected_text: str) -> None:
    """Load the config and check it fails with a problem containing `expected_text`."""
    with pytest.raises(ConfigError) as caught:
        load_config_bundle(config_dir)
    assert any(expected_text in problem for problem in caught.value.problems), caught.value


def edit_business_rules(config_dir: Path, old: str, new: str, count: int | None = 1) -> None:
    """Replace text in a config copy's `business_rules.md`.

    The text must appear exactly `count` times, or at least once when `count` is None.
    """
    path = config_dir / "business_rules.md"
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    assert found == count or (count is None and found > 0), f"{old!r} found {found} times"
    path.write_text(text.replace(old, new), encoding="utf-8")


def edit_yaml(path: Path, change: Callable[[Any], None]) -> None:
    """Load a YAML file, apply `change` to the data, and write it back."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
