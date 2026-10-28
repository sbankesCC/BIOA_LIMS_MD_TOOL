"""Chunking tests: chunk IDs, table and paragraph groups, loader headers, issue messages."""

from app.config.bundle import ConfigBundle
from app.config.issue_catalogue import fill_message
from app.ingest.chunking import ChunkIdCounter, group_paragraphs, split_table_rows
from app.ingest.loader_detection import is_loader_header
from app.ingest.xlsx import format_cell, make_sheet_token


def test_word_chunk_ids_count_in_reading_order() -> None:
    """Word chunk IDs are the document ID plus a three-digit counter."""
    counter = ChunkIdCounter("doc01")
    assert [counter.next_id(), counter.next_id()] == ["doc01-c001", "doc01-c002"]


def test_pdf_chunk_ids_include_the_page() -> None:
    """PDF chunk IDs carry the page number, as in CONTRACTS §1 (doc02-p04-c007)."""
    counter = ChunkIdCounter("doc02")
    ids = [counter.next_id(page=page) for page in (1, 1, 2, 3, 4, 4, 4)]
    assert ids[-1] == "doc02-p04-c007"


def test_small_table_stays_whole() -> None:
    """A table up to the row limit stays in one group, header included."""
    rows = ["header", "row 1", "row 2"]
    assert split_table_rows(rows, max_rows=2) == [rows]


def test_large_table_is_split_with_the_header_repeated() -> None:
    """A table over the row limit is split into groups that each start with the header."""
    rows = ["header", "row 1", "row 2", "row 3"]
    assert split_table_rows(rows, max_rows=2) == [
        ["header", "row 1", "row 2"],
        ["header", "row 3"],
    ]


def test_paragraph_groups_never_split_a_paragraph() -> None:
    """Paragraphs are grouped up to the size limit; a long paragraph stays whole."""
    paragraphs = ["a" * 6, "b" * 6, "c" * 20]
    assert group_paragraphs(paragraphs, max_characters=12) == [["a" * 6, "b" * 6], ["c" * 20]]


def test_sheet_tokens_keep_letters_and_digits_and_stay_unique() -> None:
    """Sheet names lose spaces and symbols in chunk IDs; a clash gets the sheet position."""
    used: set[str] = set()
    assert make_sheet_token("Synthetic Sheet 1", 1, used) == "sSyntheticSheet1"
    assert make_sheet_token("Synthetic-Sheet-1", 2, used) == "sSyntheticSheet12"
    assert make_sheet_token("%%", 3, used) == "s3"


def test_cell_values_are_shown_as_saved() -> None:
    """Whole floats lose '.0', other numbers and text are kept as they are."""
    assert format_cell(5.0) == "5"
    assert format_cell(0.25) == "0.25"
    assert format_cell(None) == ""
    assert format_cell("synthetic\nvalue") == "synthetic value"


def test_loader_header_needs_every_dfd_column(bundle: ConfigBundle) -> None:
    """All DFD columns (extra columns allowed) mean a loader; a partial header does not."""
    headers = bundle.dfd_template.headers
    assert is_loader_header([*headers, "synthetic extra"], headers)
    assert is_loader_header([f" {header} " for header in headers], headers)
    assert not is_loader_header(headers[:-1], headers)
    assert not is_loader_header(headers, [])


def test_fill_message_fills_known_placeholders_only() -> None:
    """Known placeholders are filled; ones without a value stay as written."""
    message = fill_message("{file} could not be read ({other}).", {"file": "synthetic.pdf"})
    assert message == "synthetic.pdf could not be read ({other})."
