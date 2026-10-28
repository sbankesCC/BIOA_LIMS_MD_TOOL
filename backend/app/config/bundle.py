"""ConfigBundle: every client config file loaded, checked against each other, with versions.

A run captures the bundle's versions at its start and keeps them for its whole life.
"""

from pathlib import Path

from pydantic import BaseModel

from app.config.dfd_template import DfdTemplate, load_dfd_template
from app.config.errors import ConfigError
from app.config.field_rules import FieldRules, load_field_rules
from app.config.issue_catalogue import IssueCatalogue, load_issue_catalogue
from app.config.lookup_lists import LookupLists, load_lookup_lists
from app.config.prompts import FOLDER_NAME as PROMPTS_FOLDER
from app.config.prompts import PromptTemplate, load_prompts
from app.config.reference_mapping import ReferenceMapping, load_reference_mapping


class ConfigVersions(BaseModel):
    """The version of each config file; prompts are versioned one by one."""

    field_rules: str
    issue_catalogue: str
    lookup_lists: str
    dfd_template: str
    reference_data_mapping: str
    prompts: dict[str, str]


class ConfigBundle(BaseModel):
    """All client config, loaded and validated."""

    config_dir: Path
    field_rules: FieldRules
    issue_catalogue: IssueCatalogue
    lookup_lists: LookupLists
    dfd_template: DfdTemplate
    reference_mapping: ReferenceMapping
    prompts: dict[str, PromptTemplate]

    def versions(self) -> ConfigVersions:
        """Return the version of every config file in this bundle."""
        return ConfigVersions(
            field_rules=self.field_rules.version,
            issue_catalogue=self.issue_catalogue.version,
            lookup_lists=self.lookup_lists.version,
            dfd_template=self.dfd_template.version,
            reference_data_mapping=self.reference_mapping.version,
            prompts={name: prompt.version for name, prompt in self.prompts.items()},
        )


def load_config_bundle(config_dir: Path) -> ConfigBundle:
    """Load every config file from `config_dir` and check them against each other."""
    if not config_dir.is_dir():
        raise ConfigError(
            [f"The config folder {config_dir} does not exist. Check CLIENT_CONFIG_DIR."]
        )
    bundle = ConfigBundle(
        config_dir=config_dir,
        field_rules=load_field_rules(config_dir / "field_rules.yaml"),
        issue_catalogue=load_issue_catalogue(config_dir / "issue_catalogue.yaml"),
        lookup_lists=load_lookup_lists(config_dir / "lookup_lists.xlsx"),
        dfd_template=load_dfd_template(config_dir / "dfd_template.xlsx"),
        reference_mapping=load_reference_mapping(config_dir / "reference_data_mapping.yaml"),
        prompts=load_prompts(config_dir / PROMPTS_FOLDER),
    )
    problems = (
        find_template_problems(bundle)
        + find_lookup_problems(bundle)
        + find_issue_code_problems(bundle)
    )
    if problems:
        raise ConfigError(problems)
    return bundle


def find_template_problems(bundle: ConfigBundle) -> list[str]:
    """Check the DFD template headers equal the field-rule columns, in the same order."""
    columns = bundle.field_rules.columns()
    headers = bundle.dfd_template.headers
    if headers == columns:
        return []
    return [
        "dfd_template.xlsx: the headers do not match the columns in field_rules.yaml "
        f"(template has {len(headers)}, field rules have {len(columns)}). "
        "They must be the same names in the same order."
    ]


def find_lookup_problems(bundle: ConfigBundle) -> list[str]:
    """Check each lookup field's sheet exists and its default is one of the sheet's values."""
    problems: list[str] = []
    sheets = bundle.lookup_lists.sheets
    for field in bundle.field_rules.fields:
        if field.lookup_sheet is None:
            continue
        if field.lookup_sheet not in sheets:
            problems.append(
                f"lookup_lists.xlsx: the sheet '{field.lookup_sheet}' used by field "
                f"'{field.key}' is missing."
            )
            continue
        # A default that is not on the list would fail the lookup check on every record
        if field.default is not None and field.default not in sheets[field.lookup_sheet]:
            problems.append(
                f"field_rules.yaml: the default of field '{field.key}' is not on the "
                f"'{field.lookup_sheet}' lookup sheet."
            )
    return problems


def find_issue_code_problems(bundle: ConfigBundle) -> list[str]:
    """Check every issue code named in the field rules is a record issue in the catalogue."""
    problems: list[str] = []
    record_codes = bundle.issue_catalogue.record_issues
    for group_name, group in bundle.field_rules.condition_groups.items():
        if group.issue_code not in record_codes:
            problems.append(
                f"field_rules.yaml: condition group '{group_name}' uses issue code "
                f"{group.issue_code}, which is not a record issue in issue_catalogue.yaml."
            )
    return problems
