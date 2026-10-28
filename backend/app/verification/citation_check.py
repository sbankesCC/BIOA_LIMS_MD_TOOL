"""Citation check (CONTRACTS §2, code): checks quoted sources against the cited chunks.

Per evidence pair, the quote must appear in its chunk; per field, the value must appear in at
least one quote. Both ignore case and whitespace; table-cell separators (`|`, which Word table
chunks put between cells) count as whitespace. Quotes on a scanned page image cannot be checked.
Writes only `verification.citation_check` of each field.
"""

from collections.abc import Mapping, Sequence

from app.contracts.chunk import Chunk
from app.contracts.extraction import Evidence, ExtractedField, ExtractedValue
from app.contracts.record import FieldVerification, StoredField, StoredRecord
from app.contracts.verification import CitationCheck

# Word table chunks join cells with " | ", so a quoted row may be written with or without it
TABLE_CELL_SEPARATOR = "|"


def normalize_for_citation(text: str) -> str:
    """Return the text without whitespace, cell separators or case, for a citation comparison."""
    without_separators = text.replace(TABLE_CELL_SEPARATOR, " ")
    return "".join(without_separators.split()).casefold()


def contains_text(container: str, text: str) -> bool:
    """Return True if `text` appears in `container`, ignoring case and whitespace."""
    return normalize_for_citation(text) in normalize_for_citation(container)


def check_quote(evidence: Evidence, chunks: Mapping[str, Chunk]) -> CitationCheck:
    """Check one evidence pair: is the quote in its chunk? Image chunks cannot be checked."""
    chunk = chunks.get(evidence.chunk_id)
    # A chunk ID that does not exist cannot back up a quote
    if chunk is None:
        return "not_verified"
    if chunk.kind == "page_image" or chunk.text is None:
        return "not_checkable"
    return "verified" if contains_text(chunk.text, evidence.quote) else "not_verified"


def check_value(
    value: ExtractedValue, evidence: Sequence[Evidence], chunks: Mapping[str, Chunk]
) -> CitationCheck:
    """Check one value and its evidence pairs; a list value needs each entry in a quote."""
    results = [check_quote(pair, chunks) for pair in evidence]
    # No evidence, or any quote missing from its chunk, fails the check
    if not results or "not_verified" in results:
        return "not_verified"
    # The value must appear in a quote that could be checked
    checked_quotes = [
        pair.quote for pair, result in zip(evidence, results, strict=True) if result == "verified"
    ]
    entries = [value] if isinstance(value, str) else value
    if all(any(contains_text(quote, entry) for quote in checked_quotes) for entry in entries):
        return "verified"
    # Not in a checked quote: if image quotes remain, the value may be there
    return "not_checkable" if "not_checkable" in results else "not_verified"


def combine_results(results: Sequence[CitationCheck]) -> CitationCheck:
    """Combine several results: any failure fails, then any unchecked, else verified."""
    if "not_verified" in results:
        return "not_verified"
    if "not_checkable" in results:
        return "not_checkable"
    return "verified"


def check_field_citations(
    extraction: ExtractedField, chunks: Mapping[str, Chunk]
) -> CitationCheck | None:
    """Return a field's citation result; None for a field with nothing to check (not found)."""
    # A found value is checked against its own evidence
    if extraction.status == "found" and extraction.value is not None:
        return check_value(extraction.value, extraction.evidence, chunks)
    # A conflict is checked per alternative, each against its own evidence
    if extraction.status == "conflicting" and extraction.alternatives:
        results: list[CitationCheck] = [
            check_value(alternative.value, alternative.evidence, chunks)
            for alternative in extraction.alternatives
        ]
        return combine_results(results)
    return None


def check_record_citations(record: StoredRecord, chunks: Mapping[str, Chunk]) -> StoredRecord:
    """Return a copy of the record with `citation_check` set on every extracted field."""
    fields = {key: check_stored_field(field, chunks) for key, field in record.fields.items()}
    return record.model_copy(update={"fields": fields})


def check_stored_field(field: StoredField, chunks: Mapping[str, Chunk]) -> StoredField:
    """Set one field's citation result, keeping the verification agent's verdict and note."""
    if field.extraction is None:
        return field
    result = check_field_citations(field.extraction, chunks)
    current = field.verification or FieldVerification()
    verification = current.model_copy(update={"citation_check": result})
    return field.model_copy(update={"verification": verification})


def index_chunks(chunks: Sequence[Chunk]) -> dict[str, Chunk]:
    """Return the chunks by chunk ID, for the citation check."""
    return {chunk.chunk_id: chunk for chunk in chunks}
