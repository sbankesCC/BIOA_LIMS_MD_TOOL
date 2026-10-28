"""Config error type and helpers shared by every config loader."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError
from pydantic_core import ErrorDetails


class ConfigError(Exception):
    """Raised when a config file is missing or broken; the message lists every problem found."""

    def __init__(self, problems: list[str]) -> None:
        """Join the problems into one readable message."""
        self.problems = problems
        lines = "\n".join(f"- {problem}" for problem in problems)
        super().__init__(
            f"The client config is broken. Fix these problems, then restart the app:\n{lines}"
        )


def require_file(path: Path) -> None:
    """Raise ConfigError if a config file does not exist."""
    if not path.is_file():
        raise ConfigError([f"{path.name}: file not found at {path}. Check CLIENT_CONFIG_DIR."])


def read_yaml(path: Path) -> Any:
    """Read a YAML config file, turning a syntax error into a ConfigError."""
    require_file(path)
    try:
        with path.open(encoding="utf-8") as file:
            return yaml.safe_load(file)
    except yaml.YAMLError as error:
        raise ConfigError([f"{path.name}: not valid YAML ({error})."]) from error


def parse_model[ModelT: BaseModel](model: type[ModelT], data: Any, file_name: str) -> ModelT:
    """Validate raw data against a Pydantic model, reporting problems with the file name."""
    try:
        return model.model_validate(data)
    except ValidationError as error:
        problems = [describe_validation_problem(file_name, item) for item in error.errors()]
        raise ConfigError(problems) from error


def describe_validation_problem(file_name: str, item: ErrorDetails) -> str:
    """Turn one Pydantic error into a short line: file, location, what is wrong."""
    location = ".".join(str(part) for part in item["loc"]) or "(top level)"
    return f"{file_name}: {location}: {item['msg']}."
