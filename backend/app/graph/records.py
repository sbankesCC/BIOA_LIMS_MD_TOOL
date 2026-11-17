"""Stored records during processing: built from extraction, merged on re-extraction, verified.

Record IDs come from code (`rec_0001`, ...), never from the LLM. A re-extraction replaces only the
affected records' extraction sections and keeps their IDs; a record it does not return is kept
unchanged and listed as dropped; new items get new IDs.
"""

from collections.abc import Collection, Mapping, Sequence

from pydantic import BaseModel

from app.agents.matching import MatchingGroup, MatchingResult
from app.config.business_rules import BusinessRules
from app.contracts.extraction import ExtractedRecord, ExtractionOutput
from app.contracts.record import (
    FieldOutput,
    FieldVerification,
    RecordExtraction,
    RecordVerification,
    StoredContextAttribute,
    StoredField,
    StoredRecord,
    Suggestion,
    find_initial_origin,
)
from app.contracts.verification import FieldVerdict, VerificationOutput
from app.ids import make_record_id_counter


class MergeResult(BaseModel):
    """The records after a re-extraction, and the affected records it did not return."""

    records: list[StoredRecord]
    dropped_record_ids: list[str]


def build_stored_record(
    record_id: str, extracted: ExtractedRecord, business_rules: BusinessRules, is_re_extracted: bool
) -> StoredRecord:
    """Wrap an extracted record with every context attribute and loader field."""
    fields: dict[str, StoredField] = {}
    for rule in business_rules.fields:
        # Fields the model does not extract get their role as origin; transformation fills outputs
        if not rule.is_extracted:
            fields[rule.key] = StoredField(output=FieldOutput(origin=find_initial_origin(rule)))
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
        context={
            attribute.key: StoredContextAttribute(extraction=extracted.context.get(attribute.key))
            for attribute in business_rules.context_fields()
        },
        fields=fields,
    )


def build_first_records(
    output: ExtractionOutput, business_rules: BusinessRules
) -> list[StoredRecord]:
    """Give every extracted record a new record ID, in response order."""
    counter = make_record_id_counter()
    return [
        build_stored_record(counter.next_id(), extracted, business_rules, is_re_extracted=False)
        for extracted in output.records
    ]


def merge_reextraction(
    records: Sequence[StoredRecord],
    output: ExtractionOutput,
    affected_ids: set[str],
    business_rules: BusinessRules,
) -> MergeResult:
    """Replace the affected records that came back, keep the others, and add new items."""
    returned = {extracted.record_ref: extracted for extracted in output.records}
    merged: list[StoredRecord] = []
    dropped: list[str] = []
    for record in records:
        extracted = returned.get(record.record_id)
        if record.record_id in affected_ids and extracted is not None:
            merged.append(build_stored_record(record.record_id, extracted, business_rules, True))
        else:
            merged.append(record)
        # An affected record the re-extraction left out is kept and flagged, never deleted
        if record.record_id in affected_ids and extracted is None:
            dropped.append(record.record_id)
    # Items not echoing an existing ID are new records with new IDs
    counter = make_record_id_counter(record.record_id for record in records)
    for extracted in output.records:
        if extracted.record_ref not in affected_ids:
            merged.append(build_stored_record(counter.next_id(), extracted, business_rules, True))
    return MergeResult(records=merged, dropped_record_ids=dropped)


def clear_agent_findings(record: StoredRecord) -> StoredRecord:
    """Remove the verification agent's earlier verdicts, keeping citation results."""
    fields = {key: clear_field_verdict(stored) for key, stored in record.fields.items()}
    context = {key: clear_field_verdict(stored) for key, stored in record.context.items()}
    verification = record.verification.model_copy(update={"findings": []})
    return record.model_copy(
        update={"fields": fields, "context": context, "verification": verification}
    )


def clear_field_verdict[Stored: StoredField | StoredContextAttribute](stored: Stored) -> Stored:
    """Remove a field's (or context attribute's) agent verdict and note, keeping its citation."""
    if stored.verification is None:
        return stored
    verification = stored.verification.model_copy(update={"verdict": None, "note": None})
    return stored.model_copy(update={"verification": verification})


def apply_findings(record: StoredRecord, findings: VerificationOutput) -> StoredRecord:
    """Write the agent's verdicts into fields and context, and record verdicts into the record."""
    fields = dict(record.fields)
    context = dict(record.context)
    for finding in findings.field_findings:
        if finding.record_id != record.record_id:
            continue
        # The finding's section says whether it names a loader field or a context attribute
        if finding.section == "context":
            write_verdict(context, finding.field, finding.verdict, finding.note)
        else:
            write_verdict(fields, finding.field, finding.verdict, finding.note)
    record_findings = [f for f in findings.record_findings if f.record_id == record.record_id]
    verification = record.verification.model_copy(update={"findings": record_findings})
    return record.model_copy(
        update={"fields": fields, "context": context, "verification": verification}
    )


def write_verdict[Stored: StoredField | StoredContextAttribute](
    entries: dict[str, Stored], key: str, verdict: FieldVerdict, note: str
) -> None:
    """Set one entry's verdict and note; unknown keys and entries not extracted are ignored."""
    stored = entries.get(key)
    if stored is None or stored.extraction is None:
        return
    current = stored.verification or FieldVerification()
    verification = current.model_copy(update={"verdict": verdict, "note": note})
    entries[key] = stored.model_copy(update={"verification": verification})


def find_matching_suggestions(
    groups: Sequence[MatchingGroup], result: MatchingResult
) -> dict[tuple[str, str], Suggestion]:
    """Return a Matching suggestion for every record field whose item got a usable choice."""
    suggestions: dict[tuple[str, str], Suggestion] = {}
    for group in groups:
        answer = result.answers.get(group.item.item_id)
        if answer is None or answer.choice is None:
            continue
        suggestion = Suggestion(
            value=answer.choice, source="matching", reason=answer.reason, rule_id=None
        )
        for target in group.targets:
            suggestions[(target.record_id, target.field)] = suggestion
    return suggestions


def apply_suggestions(
    records: Sequence[StoredRecord],
    suggestions: Mapping[tuple[str, str], Suggestion],
    field_keys: Collection[str],
) -> list[StoredRecord]:
    """Return the records with each suggestion set on its field (the only section written).

    Only the fields a step owns (`field_keys`) change; one with no new suggestion loses an old
    one, so a rerun never keeps a stale suggestion.
    """
    updated: list[StoredRecord] = []
    for record in records:
        fields = dict(record.fields)
        for key in field_keys:
            stored = record.fields.get(key)
            if stored is not None:
                suggestion = suggestions.get((record.record_id, key))
                fields[key] = stored.model_copy(update={"suggestion": suggestion})
        updated.append(record.model_copy(update={"fields": fields}))
    return updated
