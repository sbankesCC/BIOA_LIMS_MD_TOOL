"""Reference data mapping (`reference_data_mapping.yaml`): upload columns, duplicate-check rules."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.config.errors import parse_model, read_yaml

FILE_NAME = "reference_data_mapping.yaml"


class ReferenceColumns(BaseModel):
    """Column names in an existing Consumable Types export, by the name the code uses."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str | None = None
    consumable_class: str | None = None
    active_flag: str | None = None
    version_status: str | None = None


class ReferenceRules(BaseModel):
    """Duplicate-check settings."""

    model_config = ConfigDict(extra="forbid")

    exact_match_ignores_active_flag: bool
    shortlist_size: int = Field(gt=0)


class ReferenceMapping(BaseModel):
    """The whole mapping file."""

    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1)
    columns: ReferenceColumns
    rules: ReferenceRules


def load_reference_mapping(path: Path) -> ReferenceMapping:
    """Load `reference_data_mapping.yaml`; raise ConfigError if it is broken."""
    return parse_model(ReferenceMapping, read_yaml(path), FILE_NAME)
