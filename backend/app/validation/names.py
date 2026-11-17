"""Name check (8.3): an empty record name is NAME_NOT_SET, with the Naming suggestion if any.

Replaces REQUIRED_MISSING on the record name field, since it can say more. In-run duplicates
use set names only (see `duplicates.py`).
"""

from pydantic import JsonValue

from app.config.business_rules import FieldDefinition
from app.contracts.record import StoredRecord
from app.validation import codes
from app.validation.issues import IssueDraft


def check_name(record: StoredRecord, name_rule: FieldDefinition) -> list[IssueDraft]:
    """Return NAME_NOT_SET for an empty name, carrying the Naming suggestion if there is one."""
    stored = record.fields.get(name_rule.key)
    if stored is not None and stored.output.value:
        return []
    details: dict[str, JsonValue] = {}
    if stored is not None and stored.suggestion is not None:
        details["suggestion"] = stored.suggestion.model_dump(mode="json")
    return [
        IssueDraft(
            code=codes.NAME_NOT_SET,
            record_id=record.record_id,
            field=name_rule.key,
            details=details,
        )
    ]
