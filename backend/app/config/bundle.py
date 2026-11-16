"""ConfigBundle: every client config file loaded, checked against each other, with versions.

A run captures the bundle's versions at its start and keeps them for its whole life. The loader
fields are kept in the export template's column order, so every consumer sees one order.
"""

from pathlib import Path

from pydantic import BaseModel

from app.config.business_rules import FILE_NAME as BUSINESS_RULES_FILE
from app.config.business_rules import BusinessRules
from app.config.business_rules_checks import (
    find_issue_code_problems,
    find_lookup_list_problems,
    find_lookup_value_problems,
    load_business_rules,
)
from app.config.errors import ConfigError
from app.config.export_template import FILE_NAME as EXPORT_TEMPLATE_FILE
from app.config.export_template import (
    ExportTemplate,
    find_column_set_problems,
    find_type_problems,
    load_export_template,
    order_fields,
)
from app.config.extraction_rules import FILE_NAME as EXTRACTION_RULES_FILE
from app.config.extraction_rules import (
    ExtractionRules,
    find_coverage_problems,
    find_shared_rule_id_problems,
    load_extraction_rules,
)
from app.config.issue_catalogue import IssueCatalogue, load_issue_catalogue
from app.config.lookup_lists import LookupLists, load_lookup_lists
from app.config.prompts import FOLDER_NAME as PROMPTS_FOLDER
from app.config.prompts import PromptTemplate, load_prompts
from app.config.reference_mapping import ReferenceMapping, load_reference_mapping


class ConfigVersions(BaseModel):
    """The version of each config file; prompts are versioned one by one."""

    business_rules: str
    extraction_rules: str
    issue_catalogue: str
    lookup_lists: str
    export_template: str
    reference_data_mapping: str
    prompts: dict[str, str]


class ConfigBundle(BaseModel):
    """All client config, loaded and validated."""

    config_dir: Path
    business_rules: BusinessRules
    extraction_rules: ExtractionRules
    issue_catalogue: IssueCatalogue
    lookup_lists: LookupLists
    export_template: ExportTemplate
    reference_mapping: ReferenceMapping
    prompts: dict[str, PromptTemplate]

    def versions(self) -> ConfigVersions:
        """Return the version of every config file in this bundle."""
        return ConfigVersions(
            business_rules=self.business_rules.version,
            extraction_rules=self.extraction_rules.version,
            issue_catalogue=self.issue_catalogue.version,
            lookup_lists=self.lookup_lists.version,
            export_template=self.export_template.version,
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
        business_rules=load_business_rules(config_dir / BUSINESS_RULES_FILE),
        extraction_rules=load_extraction_rules(config_dir / EXTRACTION_RULES_FILE),
        issue_catalogue=load_issue_catalogue(config_dir / "issue_catalogue.yaml"),
        lookup_lists=load_lookup_lists(config_dir / "lookup_lists.xlsx"),
        export_template=load_export_template(config_dir / EXPORT_TEMPLATE_FILE),
        reference_mapping=load_reference_mapping(config_dir / "reference_data_mapping.yaml"),
        prompts=load_prompts(config_dir / PROMPTS_FOLDER),
    )
    rules = bundle.business_rules
    problems = (
        find_column_set_problems(bundle.export_template, rules)
        + find_type_problems(bundle.export_template, rules)
        + find_coverage_problems(bundle.extraction_rules, rules)
        + find_shared_rule_id_problems(bundle.extraction_rules, rules)
        + find_lookup_list_problems(rules, bundle.lookup_lists)
        + find_lookup_value_problems(rules, bundle.lookup_lists)
        + find_issue_code_problems(rules, bundle.issue_catalogue)
    )
    if problems:
        raise ConfigError(problems)
    # The export template is the only source of column order (user decision 9)
    ordered = order_fields(rules, bundle.export_template)
    return bundle.model_copy(update={"business_rules": ordered})
