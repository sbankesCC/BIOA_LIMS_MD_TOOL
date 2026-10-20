"""Issue drafts: what each check finds, turned into catalogue issues in one place.

Checks return drafts (code, where, the value that keys the issue). This module adds severity,
message and flags from the catalogue, and the stable issue ID from the key.
"""

from collections.abc import Mapping

from pydantic import BaseModel, JsonValue

from app.config.errors import ConfigError
from app.config.field_rules import FieldRules
from app.config.issue_catalogue import IssueCatalogue, IssueDefinition, fill_message
from app.contracts.issue import Issue
from app.ids import make_issue_id


class IssueDraft(BaseModel):
    """A problem a check found, before it gets its catalogue severity, message and ID.

    `value` is the current output value that keys the issue (CONTRACTS §4a), or None.
    """

    code: str
    record_id: str | None = None
    field: str | None = None
    value: str | None = None
    message_values: dict[str, str] = {}
    details: dict[str, JsonValue] = {}


def find_definition(catalogue: IssueCatalogue, draft: IssueDraft) -> IssueDefinition:
    """Return the catalogue entry for a draft: a record issue, or a run issue with no record."""
    issues = catalogue.record_issues if draft.record_id is not None else catalogue.run_issues
    definition = issues.get(draft.code)
    if definition is None:
        level = "record" if draft.record_id is not None else "run"
        raise ConfigError(
            [f"issue_catalogue.yaml: {level} issue {draft.code}, used by validation, is missing."]
        )
    return definition


def build_message_values(draft: IssueDraft, field_rules: FieldRules) -> dict[str, str]:
    """Return the placeholder values for a draft's message: field column name, value, extras."""
    values: dict[str, str] = {}
    # The user sees the field's DFD column name, not its key
    if draft.field is not None:
        columns = {rule.key: rule.column for rule in field_rules.fields}
        values["field"] = columns.get(draft.field, draft.field)
    if draft.value is not None:
        values["value"] = draft.value
    values.update(draft.message_values)
    return values


def make_issue(draft: IssueDraft, catalogue: IssueCatalogue, field_rules: FieldRules) -> Issue:
    """Build an open issue from a draft, with its catalogue severity and filled message."""
    definition = find_definition(catalogue, draft)
    message_values: Mapping[str, str] = build_message_values(draft, field_rules)
    return Issue(
        issue_id=make_issue_id(draft.code, draft.record_id, draft.field, draft.value),
        code=draft.code,
        severity=definition.severity,
        record_id=draft.record_id,
        field=draft.field,
        message=fill_message(definition.message, message_values),
        individual_review=definition.individual_review,
        details=draft.details,
    )
