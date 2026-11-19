"""Assembly (ARCHITECTURE §4.7d): writes every field's `output` section from the normalized values.

Order: loader values from normalization (closing identical conflicts), the four derivations,
then defaults. System and `blank_for_now` fields stay blank. A value a person set is never
overwritten, and a derived field is recomputed on every call, so a re-check updates it. Code
only; it writes nothing but `field.output` and creates no issues (its notes go in `changes`).
"""

from collections.abc import Sequence

from app.assembly.defaults import apply_default
from app.assembly.derivations import DERIVATIONS, Derived
from app.assembly.loader_values import build_loader_value
from app.config.business_rules import BusinessRules, FieldDefinition
from app.contracts.record import (
    FieldOutput,
    Origin,
    StoredField,
    StoredRecord,
    find_initial_origin,
)

# Origins of values a person set: Assembly never changes these
USER_ORIGINS: tuple[Origin, ...] = ("user_edited", "from_suggestion", "fixed")


def assemble_records(
    records: Sequence[StoredRecord], business_rules: BusinessRules
) -> list[StoredRecord]:
    """Return the records with every field's output section rebuilt."""
    return [assemble_record(record, business_rules) for record in records]


def assemble_record(record: StoredRecord, business_rules: BusinessRules) -> StoredRecord:
    """Return a copy of the record with each loader field's output written by Assembly."""
    fields = dict(record.fields)
    # Loader values first: the derivations read them
    for rule in business_rules.fields:
        fields[rule.key] = write_loader_value(rule, record.fields.get(rule.key))
    working = record.model_copy(update={"fields": fields})
    # Each derivation reads the outputs written before it, in a fixed order
    for derive in DERIVATIONS:
        derived = derive(business_rules, working)
        if derived is not None:
            working = apply_derived(working, derived)
    # Defaults last: they only fill what is still empty
    return apply_defaults(working, business_rules)


def write_loader_value(rule: FieldDefinition, stored: StoredField | None) -> StoredField:
    """Return the field with its output built from normalization, unless a person set it."""
    current = stored if stored is not None else StoredField(output=FieldOutput(origin="extracted"))
    if current.output.origin in USER_ORIGINS:
        return current
    if rule.is_extracted:
        return current.model_copy(update={"output": build_loader_value(rule, current)})
    # Derived, system and blank_for_now fields start blank with their role as origin
    output = FieldOutput(value=None, origin=find_initial_origin(rule))
    return current.model_copy(update={"output": output})


def apply_derived(record: StoredRecord, derived: Derived) -> StoredRecord:
    """Return the record with one derived field's output set, unless a person set it."""
    stored = record.fields[derived.key]
    if stored.output.origin in USER_ORIGINS:
        return record
    output = FieldOutput(value=derived.value, origin="derived", changes=derived.notes)
    fields = {**record.fields, derived.key: stored.model_copy(update={"output": output})}
    return record.model_copy(update={"fields": fields})


def apply_defaults(record: StoredRecord, business_rules: BusinessRules) -> StoredRecord:
    """Return the record with defaults filled into empty extracted fields."""
    fields = dict(record.fields)
    for rule in business_rules.fields:
        stored = fields[rule.key]
        if stored.output.origin in USER_ORIGINS:
            continue
        output = apply_default(rule, stored, stored.output)
        fields[rule.key] = stored.model_copy(update={"output": output})
    return record.model_copy(update={"fields": fields})
