"""Shared base for contract models: exact shapes, unknown keys rejected."""

from pydantic import BaseModel, ConfigDict


class ContractModel(BaseModel):
    """Base for every contract model; unknown keys are an error, so shapes stay exact."""

    model_config = ConfigDict(extra="forbid")
