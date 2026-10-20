"""No-client-literals test: nothing under `backend/` hard-codes client lookup values or columns.

Client content must live only in the client config folder (ARCHITECTURE §10), so a scrubbed copy
of the repo can be made. Python files are checked by their string constants; JSON by its strings.
"""

import ast
import json
from pathlib import Path
from typing import Any

from app.config.bundle import ConfigBundle
from app.settings import PROJECT_ROOT

BACKEND_DIR = PROJECT_ROOT / "backend"

# One-character values ("Y", "%", "L") are generic tokens, not client content, and would
# match ordinary code; they are left out of the check
MINIMUM_LENGTH = 2


def client_literals(bundle: ConfigBundle) -> set[str]:
    """Return every lookup value and column name from the client config worth checking."""
    values = {value for sheet in bundle.lookup_lists.sheets.values() for value in sheet}
    values |= set(bundle.field_rules.columns())
    return {value for value in values if len(value) >= MINIMUM_LENGTH}


def python_strings(path: Path) -> set[str]:
    """Return every string constant in a Python file (including docstrings and f-string parts)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def json_strings(data: Any) -> set[str]:
    """Return every string (keys and values) in parsed JSON data."""
    if isinstance(data, str):
        return {data}
    if isinstance(data, dict):
        return {s for key, value in data.items() for s in json_strings(key) | json_strings(value)}
    if isinstance(data, list):
        return {s for item in data for s in json_strings(item)}
    return set()


def backend_files() -> list[Path]:
    """Return the Python and JSON files under backend/, skipping caches."""
    files = list(BACKEND_DIR.rglob("*.py")) + list(BACKEND_DIR.rglob("*.json"))
    return [path for path in files if "__pycache__" not in path.parts]


def test_no_backend_file_contains_client_values(bundle: ConfigBundle) -> None:
    """No string in backend code or JSON equals a client lookup value or column name."""
    literals = client_literals(bundle)
    found: list[str] = []
    for path in backend_files():
        if path.suffix == ".py":
            strings = python_strings(path)
        else:
            strings = json_strings(json.loads(path.read_text(encoding="utf-8")))
        for value in sorted(strings & literals):
            found.append(f"{path.relative_to(PROJECT_ROOT)}: {value!r}")
    assert found == []


def test_check_would_catch_a_planted_value(bundle: ConfigBundle, tmp_path: Path) -> None:
    """The check finds a client value written as a string constant (proves it is not empty)."""
    planted_value = sorted(client_literals(bundle))[0]
    planted_file = tmp_path / "planted.py"
    planted_file.write_text(f"NAME = {planted_value!r}\n", encoding="utf-8")
    assert planted_value in python_strings(planted_file)
