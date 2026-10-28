"""The OpenAPI schema (the front end's contract) and the command that writes the locked copy.

Run `uv run python -m app.api` from the repo root to rewrite `backend/openapi.json`; a test
fails while the committed file differs from the generated schema.
"""

import json
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute

from app.settings import PROJECT_ROOT

OPENAPI_FILE = PROJECT_ROOT / "backend" / "openapi.json"

# Key of the generated titles that are removed from the schema
TITLE_KEY = "title"


def make_operation_id(route: APIRoute) -> str:
    """Use the route function's name as the operation ID (e.g. `list_runs`)."""
    return route.name


def build_openapi_schema(app: FastAPI) -> dict[str, Any]:
    """Return the app's OpenAPI schema without the titles generated from names.

    Generated titles ("Status", "Version") repeat the property names and would read as client
    column names; the front end's types come from the property names, not the titles.
    """
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
    )
    components = schema.get("components", {})
    schema["components"] = remove_titles(components)
    schema["paths"] = remove_titles(schema.get("paths", {}))
    return schema


def remove_titles(node: Any) -> Any:
    """Return a copy of a schema part with every generated text `title` removed."""
    if isinstance(node, dict):
        return {
            key: remove_titles(value)
            for key, value in node.items()  # pyright: ignore[reportUnknownVariableType]
            if not (key == TITLE_KEY and isinstance(value, str))
        }
    if isinstance(node, list):
        return [remove_titles(item) for item in node]  # pyright: ignore[reportUnknownVariableType]
    return node


def install_openapi(app: FastAPI) -> None:
    """Serve the title-free schema at `/openapi.json`, built once on first request."""

    def openapi() -> dict[str, Any]:
        """Return the cached schema, building it on first use."""
        if app.openapi_schema is None:
            app.openapi_schema = build_openapi_schema(app)
        return app.openapi_schema

    app.openapi = openapi


def format_schema(schema: dict[str, Any]) -> str:
    """Return the schema as the committed file holds it: indented JSON ending in a newline."""
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
