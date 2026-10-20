"""Health route (CONTRACTS §13): liveness, with the config versions in use. No sign-in needed."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.dependencies import Resources
from app.config.bundle import ConfigVersions

NO_CONFIG_MESSAGE = "No client config loaded. Set CLIENT_CONFIG_DIR in .env, then restart the app."

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Liveness answer, with the config versions in use (or why no config is loaded)."""

    status: str
    config_versions: ConfigVersions | None
    message: str | None


@router.get("/health", summary="Check the API is up")
def get_health(resources: Resources) -> HealthResponse:
    """Report that the API is up and which config versions it loaded."""
    if resources.config is None:
        return HealthResponse(status="ok", config_versions=None, message=NO_CONFIG_MESSAGE)
    return HealthResponse(status="ok", config_versions=resources.config.versions(), message=None)
