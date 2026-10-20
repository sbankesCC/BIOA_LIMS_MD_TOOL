"""Workspace: the config, stores and LLM client factory the run, review and export requests use.

The API builds one from the settings per request; tests build one with temporary folders and
a fake LLM client factory.
"""

from collections.abc import Callable
from dataclasses import dataclass

from app.admin.lookup_lists import LookupListAdmin
from app.admin.reference_data import ReferenceDataAdmin
from app.config.bundle import ConfigBundle
from app.llm.client import LLMClient
from app.settings import Settings
from app.storage.review_db import ReviewDatabase
from app.storage.run_store import RunStore

# Builds a new LLM client; called once per run start and once per judge (fake clients are stateful)
LLMClientFactory = Callable[[], LLMClient]


@dataclass(frozen=True)
class Workspace:
    """Everything a run request needs: settings, config, review database, run store, LLM."""

    settings: Settings
    bundle: ConfigBundle
    database: ReviewDatabase
    run_store: RunStore
    make_client: LLMClientFactory

    def lookup_admin(self) -> LookupListAdmin:
        """Return the lookup list admin (current version for new runs, captured ones for old)."""
        return LookupListAdmin(self.database, self.run_store.storage_dir, self.bundle)

    def reference_admin(self) -> ReferenceDataAdmin:
        """Return the reference data admin."""
        return ReferenceDataAdmin(
            self.database, self.run_store.storage_dir, self.bundle.reference_mapping
        )
