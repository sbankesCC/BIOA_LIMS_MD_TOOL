"""Stored records during processing: built from extraction, merged on re-extraction, verified.

Record IDs come from code (`rec_0001`, ...), never from the LLM. A re-extraction replaces only the
affected records' extraction sections and keeps their IDs; a record it does not return is kept
unchanged and listed as dropped; new items get new IDs.
"""

from collections.abc import Sequence

from pydantic import BaseModel

from app.config.field_rules import FieldRules
from app.contracts.extraction import ExtractedRecord, ExtractionOutput
from app.contracts.record import (
    FieldOutput,
    FieldVerification,
    RecordExtraction,
    RecordVerification,
    StoredField,
    StoredRecord,
)
from app.contracts.verification import VerificationOutput
from app.ids import make_record_id_counter


class MergeResult(BaseModel):
    """The records after a re-extraction, and the affected records it did not return."""

    records: list[StoredRecord]
    dropped_record_ids: list[str]


def build_stored_record(
    record_id: str, extracted: ExtractedRecord, field_rules: FieldRules, is_re_extracted: bool
) -> StoredRecord:
    """Wrap an extracted record with every loader field; outputs wait for transformation."""
    fields: dict[str, StoredField] = {}
    for rule in field_rules.fields:
        # Non-extracted fields get their role as origin; transformation fills every output
        if rule.role != "extracted":
            fields[rule.key] = StoredField(output=FieldOutput(origin=rule.role))
            continue
        fields[rule.key] = StoredField(
            extraction=extracted.fields.get(rule.key), output=FieldOutput(origin="extracted")
        )
    return StoredRecord(
        record_id=record_id,
        found_in=list(extracted.found_in),
        extraction=RecordExtraction(
            record_ref=extracted.record_ref,
            record_summary=extracted.record_summary,
            record_warning=extracted.record_warning,
        ),
        verification=RecordVerification(re_extracted=is_re_extracted),
        fields=fields,
    )


def build_first_records(output: ExtractionOutput, field_rules: FieldRules) -> list[StoredRecord]:
    """Give every extracted record a new record ID, in response order."""
    counter = make_record_id_counter()
    return [
        build_stored_record(counter.next_id(), extracted, field_rules, is_re_extracted=False)
        for extracted in output.records
    ]


def merge_reextraction(
    records: Sequence[StoredRecord],
    output: ExtractionOutput,
    affected_ids: set[str],
    field_rules: FieldRules,
) -> MergeResult:
    """Replace the affected records that came back, keep the others, and add new items."""
    returned = {extracted.record_ref: extracted for extracted in output.records}
    merged: list[StoredRecord] = []
    dropped: list[str] = []
    for record in records:
        extracted = returned.get(record.record_id)
        if record.record_id in affected_ids and extracted is not None:
            merged.append(build_stored_record(record.record_id, extracted, field_rules, True))
        else:
            merged.append(record)
        # An affected record the re-extraction left out is kept and flagged, never deleted
        if record.record_id in affected_ids and extracted is None:
            dropped.append(record.record_id)
    # Items not echoing an existing ID are new records with new IDs
    counter = make_record_id_counter(record.record_id for record in records)
    for extracted in output.records:
        if extracted.record_ref not in affected_ids:
            merged.append(build_stored_record(counter.next_id(), extracted, field_rules, True))
    return MergeResult(records=merged, dropped_record_ids=dropped)


def clear_agent_findings(record: StoredRecord) -> StoredRecord:
    """Remove the verification agent's earlier verdicts, keeping citation results."""
    fields = {key: clear_field_verdict(stored) for key, stored in record.fields.items()}
    verification = record.verification.model_copy(update={"findings": []})
    return record.model_copy(update={"fields": fields, "verification": verification})


def clear_field_verdict(stored: StoredField) -> StoredField:
    """Remove a field's agent verdict and note, keeping its citation result."""
    if stored.verification is None:
        return stored
    verification = stored.verification.model_copy(update={"verdict": None, "note": None})
    return stored.model_copy(update={"verification": verification})


def apply_findings(record: StoredRecord, findings: VerificationOutput) -> StoredRecord:
    """Write the agent's field verdicts into the fields and its record verdicts into the record."""
    fields = dict(record.fields)
    for finding in findings.field_findings:
        stored = fields.get(finding.field)
        # Findings on unknown records or on fields that were not extracted are ignored
        if finding.record_id != record.record_id or stored is None or stored.extraction is None:
            continue
        current = stored.verification or FieldVerification()
        verification = current.model_copy(update={"verdict": finding.verdict, "note": finding.note})
        fields[finding.field] = stored.model_copy(update={"verification": verification})
    record_findings = [f for f in findings.record_findings if f.record_id == record.record_id]
    verification = record.verification.model_copy(update={"findings": record_findings})
    return record.model_copy(update={"fields": fields, "verification": verification})
