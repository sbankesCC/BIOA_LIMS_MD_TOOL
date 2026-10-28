"""Synthetic fake-LLM replies for graph tests, built from the synthetic Word method's reagent table.

Every value is copied from the synthetic document (`make_documents.REAGENT_TABLE`); fields the
document does not give are not_found. Field keys come from the client config, never written here.
"""

import json
from collections.abc import Sequence

from app.config.field_rules import FieldRules
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


def make_extracted_record(field_rules: FieldRules, ref: str, row_number: int) -> ExtractedRecord:
    """Return a record for one table row: its name and catalog number found, the rest not_found."""
    row = REAGENT_TABLE[row_number]
    quote = table_row_quote(row_number)
    name_key = field_rules.record_name_field().key
    fields: dict[str, ExtractedField] = {}
    for rule in field_rules.extracted_fields():
        if rule.key == name_key:
            fields[rule.key] = found_field(row[NAME_COLUMN], quote)
        elif rule.multi_value:
            fields[rule.key] = found_field([row[CATALOG_COLUMN]], quote)
        else:
            fields[rule.key] = ExtractedField(status="not_found")
    return ExtractedRecord(
        record_ref=ref,
        found_in=[TABLE_CHUNK_ID],
        record_summary="synthetic reagent from the synthetic table",
        fields=fields,
    )


def extraction_reply(field_rules: FieldRules, rows: Sequence[tuple[str, int]]) -> str:
    """Return an extraction reply with one record per (record_ref, table row number)."""
    records = [make_extracted_record(field_rules, ref, row) for ref, row in rows]
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


def unsupported_name(field_rules: FieldRules, record_id: str) -> FieldFinding:
    """Return an `unsupported` finding on a record's name field."""
    return FieldFinding(
        record_id=record_id,
        field=field_rules.record_name_field().key,
        verdict="unsupported",
        sources=[TABLE_CHUNK_ID],
        note="synthetic finding",
    )


def empty_extraction_reply() -> str:
    """Return an extraction reply with no records and no excluded items."""
    return json.dumps({"records": [], "excluded_items": []})
