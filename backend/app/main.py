"""FastAPI app factory: loads and validates the client config at startup and serves the API.

Run from `backend/` with `uv run uvicorn app.main:app --reload`.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from pydantic import BaseModel

from app.config.bundle import ConfigBundle, ConfigVersions, load_config_bundle
from app.logging_setup import setup_logging
from app.settings import Settings, load_settings

NO_CONFIG_MESSAGE = "No client config loaded. Set CLIENT_CONFIG_DIR in .env, then restart the app."


class HealthResponse(BaseModel):
    """Liveness answer, with the config versions in use (or why no config is loaded)."""

    status: str
    config_versions: ConfigVersions | None
    message: str | None


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app; the config is loaded and validated when the app starts."""
    app_settings = settings if settings is not None else load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        """Load the config once at startup; a broken config stops the app with its problems."""
        setup_logging()
        app.state.config = load_startup_config(app_settings)
        yield

    app = FastAPI(title="Consumable Type Extractor", lifespan=lifespan)
    app.state.settings = app_settings
    app.state.config = None

    @app.get("/health")
    def get_health(request: Request) -> HealthResponse:
        """Report that the API is up and which config versions it loaded."""
        config: ConfigBundle | None = request.app.state.config
        if config is None:
            return HealthResponse(
                status="ok",
                config_versions=None,
                message=NO_CONFIG_MESSAGE,
            )
        return HealthResponse(status="ok", config_versions=config.versions(), message=None)

    return app


def load_startup_config(settings: Settings) -> ConfigBundle | None:
    """Load the client config when CLIENT_CONFIG_DIR is set; blank means none is loaded yet."""
    if settings.client_config_dir is None:
        return None
    return load_config_bundle(settings.require_path("CLIENT_CONFIG_DIR"))


app = create_app()
