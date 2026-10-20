"""Citation check tests (CONTRACTS §2): verified, not_verified and not_checkable, per field."""

from app.contracts.chunk import Chunk
from app.contracts.extraction import Alternative, Evidence, ExtractedField
from app.contracts.record import (
    FieldOutput,
    FieldVerification,
    RecordExtraction,
    StoredField,
    StoredRecord,
)
from app.verification.citation_check import (
    check_field_citations,
    check_record_citations,
    index_chunks,
)

TEXT_CHUNK = Chunk(
    chunk_id="doc01-c001",
    document_id="doc01",
    page=None,
    section="6.2 Synthetic reagents",
    sheet=None,
    row_range=None,
    kind="table_rows",
    is_scanned=False,
    text="Synthetic antibody | 1 mL vial | Vendor Syn | Cat. SYN-1 or SYN-2\nStore at  -20 °C.",
    image_ref=None,
)
IMAGE_CHUNK = Chunk(
    chunk_id="doc02-p01-c001",
    document_id="doc02",
    page=1,
    section=None,
    sheet=None,
    row_range=None,
    kind="page_image",
    is_scanned=True,
    text=None,
    image_ref="runs/run_synthetic/pages/doc02-p01-c001.png",
)
CHUNKS = index_chunks([TEXT_CHUNK, IMAGE_CHUNK])

ROW_QUOTE = Evidence(
    chunk_id="doc01-c001",
    quote="synthetic ANTIBODY | 1 mL vial | Vendor Syn | Cat. SYN-1 or SYN-2",
)
IMAGE_QUOTE = Evidence(chunk_id="doc02-p01-c001", quote="Vendor Syn kit")


def found(value: str | list[str], evidence: list[Evidence]) -> ExtractedField:
    """Return a found field with the given value and evidence."""
    return ExtractedField(status="found", value=value, evidence=evidence)


def test_quote_and_value_in_chunk_is_verified() -> None:
    """The quote is in its chunk (case ignored) and the value is in the quote."""
    assert check_field_citations(found("Vendor Syn", [ROW_QUOTE]), CHUNKS) == "verified"


def test_whitespace_differences_are_ignored() -> None:
    """Extra or missing whitespace in the quote or value does not fail the check."""
    quote = Evidence(chunk_id="doc01-c001", quote="Store at -20°C.")
    assert check_field_citations(found("-20  °C", [quote]), CHUNKS) == "verified"


def test_quote_not_in_chunk_is_not_verified() -> None:
    """A quote that does not appear in its chunk fails the check."""
    invented = Evidence(chunk_id="doc01-c001", quote="Synthetic antibody, Vendor Other")
    assert check_field_citations(found("Vendor Other", [invented]), CHUNKS) == "not_verified"


def test_value_not_in_any_quote_is_not_verified() -> None:
    """A real quote that does not contain the value fails the check (invented value)."""
    assert check_field_citations(found("Vendor Other", [ROW_QUOTE]), CHUNKS) == "not_verified"


def test_one_bad_quote_fails_the_field() -> None:
    """Every evidence pair must check out, even when another pair is fine."""
    invented = Evidence(chunk_id="doc01-c001", quote="not in the synthetic chunk")
    field = found("Vendor Syn", [ROW_QUOTE, invented])
    assert check_field_citations(field, CHUNKS) == "not_verified"


def test_unknown_chunk_is_not_verified() -> None:
    """A quote citing a chunk that does not exist fails the check."""
    missing = Evidence(chunk_id="doc09-c001", quote="Vendor Syn")
    assert check_field_citations(found("Vendor Syn", [missing]), CHUNKS) == "not_verified"


def test_image_only_source_is_not_checkable() -> None:
    """A value cited only from a scanned page image cannot be checked."""
    assert check_field_citations(found("Vendor Syn", [IMAGE_QUOTE]), CHUNKS) == "not_checkable"


def test_text_quote_with_value_verifies_despite_image_quote() -> None:
    """A value backed by a checked text quote is verified, even with an image quote too."""
    field = found("Vendor Syn", [ROW_QUOTE, IMAGE_QUOTE])
    assert check_field_citations(field, CHUNKS) == "verified"


def test_list_value_needs_every_entry_in_a_quote() -> None:
    """Each catalog-number style entry of a list value must appear in a quote."""
    assert check_field_citations(found(["SYN-1", "SYN-2"], [ROW_QUOTE]), CHUNKS) == "verified"
    field = found(["SYN-1", "SYN-3"], [ROW_QUOTE])
    assert check_field_citations(field, CHUNKS) == "not_verified"


def test_conflicting_field_checks_each_alternative() -> None:
    """A conflict is verified only when every alternative is backed by its own evidence."""
    good = Alternative(value="1 mL", evidence=[ROW_QUOTE])
    bad = Alternative(value="5 mL", evidence=[ROW_QUOTE])
    image = Alternative(value="kit", evidence=[IMAGE_QUOTE])

    def conflict(alternatives: list[Alternative]) -> ExtractedField:
        """Return a conflicting field with these alternatives."""
        return ExtractedField(status="conflicting", alternatives=alternatives, warning="w")

    assert check_field_citations(conflict([good, image]), CHUNKS) == "not_checkable"
    assert check_field_citations(conflict([good, bad, image]), CHUNKS) == "not_verified"


def test_not_found_field_has_no_result() -> None:
    """A not-found field has nothing to check."""
    assert check_field_citations(ExtractedField(status="not_found"), CHUNKS) is None


def test_record_check_sets_only_citation_result() -> None:
    """The record check writes `citation_check` and keeps the agent's verdict and note."""
    verification = FieldVerification(verdict="unsupported", note="synthetic note")
    checked_field = StoredField(
        extraction=found("Vendor Syn", [ROW_QUOTE]),
        verification=verification,
        output=FieldOutput(origin="extracted"),
    )
    blank_field = StoredField(output=FieldOutput(origin="blank_for_now"))
    record = StoredRecord(
        record_id="rec_0001",
        found_in=["doc01-c001"],
        extraction=RecordExtraction(record_ref="R1", record_summary="synthetic record"),
        fields={"synthetic_found": checked_field, "synthetic_blank": blank_field},
    )
    result = check_record_citations(record, CHUNKS)
    assert result.fields["synthetic_found"].verification == FieldVerification(
        citation_check="verified", verdict="unsupported", note="synthetic note"
    )
    assert result.fields["synthetic_blank"] == blank_field


def test_table_row_quote_without_pipes_is_verified() -> None:
    """A quote of a Word table row written without the cell separators still matches."""
    quote = Evidence(
        chunk_id="doc01-c001", quote="Synthetic antibody 1 mL vial Vendor Syn Cat. SYN-1 or SYN-2"
    )
    assert check_field_citations(found("Vendor Syn", [quote]), CHUNKS) == "verified"


def test_value_with_cells_separated_by_pipes_still_matches() -> None:
    """A value that spans cells and keeps the pipes is found in the quote."""
    value = "1 mL vial | Vendor Syn"
    assert check_field_citations(found(value, [ROW_QUOTE]), CHUNKS) == "verified"


def test_value_spanning_cells_without_pipes_matches_a_quote_with_pipes() -> None:
    """A value written across two cells without the pipe is found in a quote that has it."""
    assert check_field_citations(found("1 mL vial Vendor Syn", [ROW_QUOTE]), CHUNKS) == "verified"
