"""Writes the locked OpenAPI schema to `backend/openapi.json`.

Run from the repo root: `uv run python -m app.api`. Review the diff before committing it.
"""

from app.api.openapi import OPENAPI_FILE, format_schema
from app.main import create_app
from app.settings import load_settings


def main() -> None:
    """Build the app with settings from the environment only and write its schema."""
    app = create_app(load_settings(env_file=None))
    OPENAPI_FILE.write_text(format_schema(app.openapi()), encoding="utf-8", newline="\n")
    print(f"Wrote {OPENAPI_FILE}")


if __name__ == "__main__":
    main()
