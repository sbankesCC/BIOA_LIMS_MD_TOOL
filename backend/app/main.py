"""FastAPI app factory: loads and validates the client config at startup and serves the API.

Run from `backend/` with `uv run uvicorn app.main:app --reload`. The app starts with every
setting blank; a request that needs a blank setting gets an error naming it.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import routes_admin, routes_exports, routes_health, routes_review, routes_runs
from app.api.dependencies import AppResources
from app.api.errors import register_error_handlers
from app.api.openapi import install_openapi, make_operation_id
from app.logging_setup import setup_logging
from app.settings import Settings, load_settings

API_TITLE = "Consumable Type Extractor"
API_VERSION = "0.1.0"
API_DESCRIPTION = (
    "Reads lab documents, extracts Consumable Type records, supports their review, and writes "
    "the DFD loader with an audit workbook. Every error has the shape "
    '`{"error": {"code", "message", "details"}}`.'
)

# Route groups, in the order the API description lists them
ROUTERS = (
    routes_health.router,
    routes_runs.router,
    routes_review.router,
    routes_exports.router,
    routes_admin.router,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app; the config is loaded and validated when the app starts."""
    resources = AppResources(settings if settings is not None else load_settings())

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        """Load the config once at startup (a broken config stops the app); close at the end."""
        setup_logging()
        resources.start()
        yield
        resources.close()

    app = FastAPI(
        title=API_TITLE,
        version=API_VERSION,
        description=API_DESCRIPTION,
        lifespan=lifespan,
        generate_unique_id_function=make_operation_id,
    )
    app.state.resources = resources
    for router in ROUTERS:
        app.include_router(router)
    register_error_handlers(app)
    install_openapi(app)
    return app


app = create_app()
