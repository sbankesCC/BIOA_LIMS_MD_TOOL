"""Synthetic fake-LLM replies for graph tests, built from the synthetic Word method's reagent table.

Every value is copied from the synthetic document (`make_documents.REAGENT_TABLE`); fields the
document does not give are not_found. Field keys come from the client config, never written here.
"""

import json
from collections.abc import Mapping, Sequence

from app.config.business_rules import BusinessRules
from app.contracts.extraction import (
    Evidence,
    ExtractedField,
    ExtractedRecord,
    ExtractionOutput,
)
from app.contracts.verification import (
    FieldFinding,
    MissedCandidate,
    VerificationOutput,
)
from tests.fixtures.make_documents import REAGENT_TABLE

# The synthetic Word method is uploaded first; its reagent table is its third chunk
TABLE_CHUNK_ID = "doc01-c003"

# Word table chunks join cells with " | "
CELL_SEPARATOR = " | "

# Columns of the synthetic reagent table
NAME_COLUMN = 0
CATALOG_COLUMN = 2


def table_row_quote(row_number: int) -> str:
    """Return one data row of the synthetic table exactly as the chunk holds it."""
    return CELL_SEPARATOR.join(REAGENT_TABLE[row_number])


def found_field(value: str | list[str], quote: str) -> ExtractedField:
    """Return a found field quoting the synthetic table chunk."""
    evidence = [Evidence(chunk_id=TABLE_CHUNK_ID, quote=quote)]
    return ExtractedField(status="found", value=value, evidence=evidence)


def make_extracted_record(
    business_rules: BusinessRules,
    ref: str,
    row_number: int,
    found_values: Mapping[str, str] | None = None,
) -> ExtractedRecord:
    """Return a record for one table row: its name and catalog number found, the rest not_found."""
    row = REAGENT_TABLE[row_number]
    quote = table_row_quote(row_number)
    name_key = business_rules.record_name_field().key
    fields: dict[str, ExtractedField] = {}
    for rule in business_rules.extracted_fields():
        if rule.key == name_key:
            fields[rule.key] = found_field(row[NAME_COLUMN], quote)
        elif rule.multi_value:
            fields[rule.key] = found_field([row[CATALOG_COLUMN]], quote)
        elif found_values and rule.key in found_values:
            fields[rule.key] = found_field(found_values[rule.key], quote)
        else:
            fields[rule.key] = ExtractedField(status="not_found")
    # The synthetic table gives no context attribute, so each one is not_found
    context = {
        attribute.key: ExtractedField(status="not_found")
        for attribute in business_rules.context_fields()
    }
    return ExtractedRecord(
        record_ref=ref,
        found_in=[TABLE_CHUNK_ID],
        record_summary="synthetic reagent from the synthetic table",
        context=context,
        fields=fields,
    )


def extraction_reply(
    business_rules: BusinessRules,
    rows: Sequence[tuple[str, int]],
    found_values: Mapping[str, str] | None = None,
) -> str:
    """Return an extraction reply with one record per (record_ref, table row number).

    `found_values` adds fields found with these values (quoting the row) on every record.
    """
    records = [make_extracted_record(business_rules, ref, row, found_values) for ref, row in rows]
    return ExtractionOutput(records=records, excluded_items=[]).model_dump_json()


def verification_reply(
    field_findings: Sequence[FieldFinding] = (), missed: Sequence[MissedCandidate] = ()
) -> str:
    """Return a verification reply with the given problems (none by default)."""
    output = VerificationOutput(
        field_findings=list(field_findings),
        record_findings=[],
        missed_candidates=list(missed),
        excluded_item_challenges=[],
        unreported_conflicts=[],
    )
    return output.model_dump_json()


def missed_row(row_number: int) -> MissedCandidate:
    """Return a missed candidate for a synthetic table row."""
    return MissedCandidate(
        name_as_written=REAGENT_TABLE[row_number][NAME_COLUMN],
        sources=[TABLE_CHUNK_ID],
        reason="synthetic: listed in the table but not extracted",
    )


def unsupported_name(business_rules: BusinessRules, record_id: str) -> FieldFinding:
    """Return an `unsupported` finding on a record's name field."""
    return FieldFinding(
        record_id=record_id,
        field=business_rules.record_name_field().key,
        verdict="unsupported",
        sources=[TABLE_CHUNK_ID],
        note="synthetic finding",
    )


def empty_extraction_reply() -> str:
    """Return an extraction reply with no records and no excluded items."""
    return json.dumps({"records": [], "excluded_items": []})


def naming_reply(answers: Sequence[tuple[str, str | None]]) -> str:
    """Return a Naming reply: one (record_id, name) per record; a None name gives no rule."""
    names = [
        {
            "record_id": record_id,
            "name": name,
            "rule_id": None if name is None else "SYN-NM",
            "reason": "synthetic reason",
        }
        for record_id, name in answers
    ]
    return json.dumps({"names": names})


def matching_reply(answers: Sequence[tuple[str, str | None]]) -> str:
    """Return a Matching reply: one (item_id, choice) per item."""
    items = [
        {"item_id": item_id, "choice": choice, "reason": "synthetic reason"}
        for item_id, choice in answers
    ]
    return json.dumps({"answers": items})


def plausibility_reply(findings: Sequence[tuple[str, str, list[str]]]) -> str:
    """Return a plausibility reply: one (record_id, check_id, fields) per finding."""
    items = [
        {"record_id": record_id, "check_id": check_id, "fields": fields, "reason": "synthetic"}
        for record_id, check_id, fields in findings
    ]
    return json.dumps({"findings": items})
