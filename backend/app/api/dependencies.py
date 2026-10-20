"""Route dependencies: the app's shared resources and the workspace each run request uses.

Resources open lazily, so the app starts with every setting blank; a request that needs a
blank setting gets the error that names it. Tests override `get_llm_client_factory` (fake LLM)
and `get_task_runner` (a runner they can wait on).
"""

from datetime import UTC, datetime
from threading import Lock
from typing import Annotated

from fastapi import Depends, Request

from app.config.bundle import ConfigBundle, load_config_bundle
from app.llm.client import LLMClient
from app.llm.provider import make_llm_client
from app.runs.background import TaskRunner, ThreadTaskRunner
from app.runs.workspace import LLMClientFactory, Workspace
from app.settings import MissingSettingError, Settings
from app.storage.review_db import ReviewDatabase
from app.storage.run_store import RunStore


class AppResources:
    """What the app opens once and shares: config, review database, background runner."""

    def __init__(self, settings: Settings) -> None:
        """Keep the settings; nothing is opened until the app starts or a request needs it."""
        self.settings = settings
        self.config: ConfigBundle | None = None
        self.database: ReviewDatabase | None = None
        self.task_runner: ThreadTaskRunner | None = None
        self.lock = Lock()

    def start(self) -> None:
        """Load the config (blank CLIENT_CONFIG_DIR loads none) and start the background runner."""
        if self.settings.client_config_dir is not None:
            self.config = load_config_bundle(self.settings.require_path("CLIENT_CONFIG_DIR"))
        self.task_runner = ThreadTaskRunner()

    def close(self) -> None:
        """Stop the background runner and close the review database."""
        if self.task_runner is not None:
            self.task_runner.shutdown()
        if self.database is not None:
            self.database.close()
            self.database = None

    def require_config(self) -> ConfigBundle:
        """Return the loaded config; a blank CLIENT_CONFIG_DIR names the setting."""
        if self.config is None:
            raise MissingSettingError("CLIENT_CONFIG_DIR")
        return self.config

    def open_database(self) -> ReviewDatabase:
        """Return the review database at REVIEW_DB, opening it on first use."""
        with self.lock:
            if self.database is None:
                self.database = ReviewDatabase(self.settings.require_path("REVIEW_DB"))
            return self.database


def get_resources(request: Request) -> AppResources:
    """Return the app's shared resources."""
    return request.app.state.resources


Resources = Annotated[AppResources, Depends(get_resources)]


def get_llm_client_factory(resources: Resources) -> LLMClientFactory:
    """Return the factory of the client LLM_PROVIDER names (built only when a feature calls it)."""
    settings = resources.settings

    def make_client() -> LLMClient:
        """Build the configured client; blank settings are named when it is built."""
        return make_llm_client(settings, settings.require_path("STORAGE_DIR"))

    return make_client


def get_task_runner(resources: Resources) -> TaskRunner:
    """Return the background runner that processes new runs."""
    if resources.task_runner is None:
        resources.task_runner = ThreadTaskRunner()
    return resources.task_runner


def get_workspace(
    resources: Resources,
    make_client: Annotated[LLMClientFactory, Depends(get_llm_client_factory)],
) -> Workspace:
    """Return the workspace; needs CLIENT_CONFIG_DIR, REVIEW_DB and STORAGE_DIR."""
    return Workspace(
        settings=resources.settings,
        bundle=resources.require_config(),
        database=resources.open_database(),
        run_store=RunStore(resources.settings.require_path("STORAGE_DIR")),
        make_client=make_client,
    )


def current_time() -> datetime:
    """Return the time stored with changes, exports and admin actions (UTC)."""
    return datetime.now(UTC)


# Route parameter types
WorkspaceDependency = Annotated[Workspace, Depends(get_workspace)]
TaskRunnerDependency = Annotated[TaskRunner, Depends(get_task_runner)]
