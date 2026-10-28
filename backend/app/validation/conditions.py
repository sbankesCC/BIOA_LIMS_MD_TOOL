"""Condition groups (`field_rules.yaml`): cross-field rules checked on each record.

`one_of`: at least one option (a set of fields) is completely filled.
`both_or_neither`: the fields are all filled or all empty. Each group names its own issue code.
"""

from app.config.field_rules import BothOrNeitherGroup, FieldRules, OneOfGroup
from app.contracts.record import StoredRecord
from app.validation.issues import IssueDraft


def is_filled(record: StoredRecord, key: str) -> bool:
    """Return True if the record's field has a non-empty output value."""
    stored = record.fields.get(key)
    return stored is not None and bool(stored.output.value)


def is_group_met(record: StoredRecord, group: OneOfGroup | BothOrNeitherGroup) -> bool:
    """Return True if the record meets one condition group."""
    if isinstance(group, OneOfGroup):
        return any(all(is_filled(record, key) for key in option) for option in group.options)
    filled = [is_filled(record, key) for key in group.fields]
    return all(filled) or not any(filled)


def check_conditions(record: StoredRecord, field_rules: FieldRules) -> list[IssueDraft]:
    """Return a record-level issue for each condition group the record does not meet."""
    drafts: list[IssueDraft] = []
    for group_name, group in field_rules.condition_groups.items():
        if not is_group_met(record, group):
            drafts.append(
                IssueDraft(
                    code=group.issue_code,
                    record_id=record.record_id,
                    details={"condition_group": group_name},
                )
            )
    return drafts
