"""OpenAPI lock: the generated schema must equal the committed `backend/openapi.json`.

It must also serve every endpoint CONTRACTS §13 lists, and nothing else.

After an intended API change, run `uv run python -m app.api` and review the diff of the file.
"""

import json
import re

import pytest
from fastapi.testclient import TestClient

from app.api.openapi import OPENAPI_FILE, format_schema
from app.main import create_app
from app.settings import PROJECT_ROOT, load_settings

CONTRACTS_FILE = PROJECT_ROOT / "docs" / "CONTRACTS.md"

# A row of the §13 endpoint table: | METHOD | /path | Does |
ENDPOINT_ROW = re.compile(r"^\| (GET|POST|PATCH|PUT|DELETE) \| (\S+) \|")

LOCK_MESSAGE = (
    "The API schema differs from backend/openapi.json. If the change is intended, run "
    "`uv run python -m app.api` from the repo root and review the diff."
)

pytestmark = pytest.mark.usefixtures("blank_environment")


def generate_schema() -> dict[str, object]:
    """Return the schema of an app built with blank settings, as the file would hold it."""
    app = create_app(load_settings(env_file=None))
    return json.loads(format_schema(app.openapi()))


def read_contract_endpoints() -> set[tuple[str, str]]:
    """Return every (method, path) in the CONTRACTS §13 table, query strings removed."""
    endpoints: set[tuple[str, str]] = set()
    for line in CONTRACTS_FILE.read_text(encoding="utf-8").splitlines():
        match = ENDPOINT_ROW.match(line)
        if match is not None:
            endpoints.add((match.group(1), match.group(2).split("?")[0]))
    return endpoints


def test_generated_schema_matches_the_locked_file() -> None:
    """The committed schema is the one the app generates (this is the lock)."""
    committed = json.loads(OPENAPI_FILE.read_text(encoding="utf-8"))
    assert generate_schema() == committed, LOCK_MESSAGE


def test_served_schema_matches_the_locked_file() -> None:
    """`GET /openapi.json` serves the locked schema."""
    with TestClient(create_app(load_settings(env_file=None))) as client:
        served = client.get("/openapi.json").json()
    assert served == json.loads(OPENAPI_FILE.read_text(encoding="utf-8"))


def test_every_contract_endpoint_is_served_and_nothing_else() -> None:
    """The schema has exactly the endpoints of CONTRACTS §13."""
    paths = generate_schema()["paths"]
    assert isinstance(paths, dict)
    served = {(method.upper(), path) for path, operations in paths.items() for method in operations}
    contract = read_contract_endpoints()
    assert len(contract) == 25
    assert served == contract


def test_every_error_response_has_the_error_shape() -> None:
    """Every declared 4xx/5xx response uses the one error model."""
    paths = generate_schema()["paths"]
    assert isinstance(paths, dict)
    for operations in paths.values():
        for operation in operations.values():
            for status, response in operation["responses"].items():
                if status.startswith(("4", "5")):
                    schema = response["content"]["application/json"]["schema"]
                    assert schema == {"$ref": "#/components/schemas/ErrorResponse"}
