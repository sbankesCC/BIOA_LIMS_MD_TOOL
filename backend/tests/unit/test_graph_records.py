"""Stored record building tests: context attributes are wrapped and receive their own findings.

Synthetic records only; field and context keys are read from the client business rules.
"""

from app.config.bundle import ConfigBundle
from app.contracts.extraction import Evidence, ExtractedField, ExtractionOutput
from app.contracts.record import StoredRecord
from app.contracts.verification import FieldFinding, VerificationOutput
from app.graph.records import apply_findings, build_first_records, clear_agent_findings
from tests.fixtures.fake_llm import make_extracted_record

FOUND_CONTEXT = ExtractedField(
    status="found",
    value="synthetic heading",
    evidence=[Evidence(chunk_id="doc01-c003", quote="synthetic heading")],
)


def build_record(bundle: ConfigBundle) -> StoredRecord:
    """Return one stored record whose first context attribute was found."""
    extracted = make_extracted_record(bundle.business_rules, "R1", 1)
    context_key = bundle.business_rules.context_fields()[0].key
    extracted.context[context_key] = FOUND_CONTEXT
    output = ExtractionOutput(records=[extracted], excluded_items=[])
    return build_first_records(output, bundle.business_rules)[0]


def make_findings(section: str, key: str) -> VerificationOutput:
    """Return verification output with one `contradicted` finding on the given key."""
    finding = FieldFinding.model_validate(
        {
            "record_id": "rec_0001",
            "section": section,
            "field": key,
            "verdict": "contradicted",
            "sources": ["doc01-c003"],
            "note": "synthetic note",
        }
    )
    return VerificationOutput(
        field_findings=[finding],
        record_findings=[],
        missed_candidates=[],
        excluded_item_challenges=[],
        unreported_conflicts=[],
    )


def test_stored_record_holds_every_context_attribute(bundle: ConfigBundle) -> None:
    """Each context attribute is kept apart from the loader fields, with its extraction."""
    record = build_record(bundle)
    context_keys = [attribute.key for attribute in bundle.business_rules.context_fields()]
    assert list(record.context) == context_keys
    assert record.context[context_keys[0]].extraction == FOUND_CONTEXT
    assert not set(context_keys) & set(record.fields)


def test_context_finding_is_written_to_the_context_attribute(bundle: ConfigBundle) -> None:
    """A finding with section `context` sets the attribute's verdict, not a field's."""
    key = bundle.business_rules.context_fields()[0].key
    record = apply_findings(build_record(bundle), make_findings("context", key))
    verification = record.context[key].verification
    assert verification is not None and verification.verdict == "contradicted"
    assert all(field.verification is None for field in record.fields.values())


def test_context_key_in_the_fields_section_is_ignored(bundle: ConfigBundle) -> None:
    """A context key sent with section `fields` names no loader field, so nothing changes."""
    record = build_record(bundle)
    key = bundle.business_rules.context_fields()[0].key
    assert apply_findings(record, make_findings("fields", key)) == record


def test_clearing_findings_clears_context_verdicts(bundle: ConfigBundle) -> None:
    """Before re-verification, context verdicts are removed like field verdicts."""
    key = bundle.business_rules.context_fields()[0].key
    record = apply_findings(build_record(bundle), make_findings("context", key))
    cleared = clear_agent_findings(record).context[key].verification
    assert cleared is not None and cleared.verdict is None
