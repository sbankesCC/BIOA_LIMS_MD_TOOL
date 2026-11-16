"""Run fields query for the API: each loader field with the values the review screen may offer.

List values come from the lookup list version the run captured at its start, not the admin's
current one (ARCHITECTURE §6); boolean fields offer the values validation accepts.
"""

from app.config.business_rules import FieldDefinition
from app.config.lookup_lists import LookupLists
from app.contracts.api import RunField, RunFieldList
from app.normalization.lookup_matching import BOOLEAN_VALUES
from app.runs.workspace import Workspace


def list_run_fields(workspace: Workspace, run_id: str) -> RunFieldList:
    """Return every loader field of a run in loader order, with its allowed values."""
    run = workspace.database.read_run(run_id)
    lookup_lists = workspace.lookup_admin().load_lookup_lists(run.config_versions.lookup_lists)
    business_rules = workspace.bundle.business_rules
    return RunFieldList(
        business_rules_version=business_rules.version,
        lookup_lists_version=lookup_lists.version,
        fields=[describe_field(rule, lookup_lists) for rule in business_rules.fields],
    )


def describe_field(rule: FieldDefinition, lookup_lists: LookupLists) -> RunField:
    """Return one field's settings and the values a dropdown may offer for it."""
    return RunField(
        key=rule.key,
        column=rule.column,
        role=rule.role,
        requirement=rule.requirement,
        type=rule.type,
        max_length=rule.max_length,
        has_lookup_list=rule.lookup_sheet is not None,
        is_boolean=rule.type == "boolean",
        multi_value=rule.multi_value,
        separator=rule.separator,
        allowed_values=find_allowed_values(rule, lookup_lists),
        is_record_name=rule.is_record_name,
    )


def find_allowed_values(rule: FieldDefinition, lookup_lists: LookupLists) -> list[str]:
    """Return a list field's lookup values, a boolean's accepted values, or none."""
    if rule.lookup_sheet is not None:
        return list(lookup_lists.sheets.get(rule.lookup_sheet, []))
    if rule.type == "boolean":
        return list(BOOLEAN_VALUES)
    return []
