"""Ingest tests on synthetic documents: chunk IDs and kinds per format, run issues, stable IDs."""

from dataclasses import dataclass
from pathlib import Path

import pytest

from app.config.bundle import ConfigBundle
from app.config.errors import ConfigError
from app.contracts.chunk import Chunk
from app.ingest.ingest import IngestResult, ingest_run
from app.storage.run_store import RunFolder, RunStore
from tests.fixtures import make_documents as files

# Upload order for the full run, so document IDs are known: doc01 is the Word method, ...
UPLOAD_ORDER = [
    files.WORD_FILE,
    files.LARGE_TABLE_WORD_FILE,
    files.TEXT_PDF_FILE,
    files.SCANNED_PDF_FILE,
    files.WORKBOOK_FILE,
    files.LOADER_FILE,
    files.BROKEN_FILE,
]

# PNG files start with this signature
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass
class IngestedRun:
    """A run folder after ingest, and the ingest result."""

    folder: RunFolder
    result: IngestResult


def ingest_files(
    storage_dir: Path, run_id: str, paths: list[Path], bundle: ConfigBundle
) -> IngestedRun:
    """Create a run, upload the files in order, and ingest it."""
    folder = RunStore(storage_dir).create_run(run_id)
    for path in paths:
        folder.save_upload(path.name, path.read_bytes())
    return IngestedRun(folder=folder, result=ingest_run(folder, bundle))


def chunks_of(result: IngestResult, document_id: str) -> list[Chunk]:
    """Return one document's chunks in order."""
    return [chunk for chunk in result.chunks if chunk.document_id == document_id]


def issue_codes(result: IngestResult) -> dict[str, str]:
    """Return each run issue's code by the document ID in its details."""
    return {str(issue.details["document_id"]): issue.code for issue in result.issues}


@pytest.fixture(scope="module")
def ingested(
    tmp_path_factory: pytest.TempPathFactory,
    synthetic_documents: dict[str, Path],
    bundle: ConfigBundle,
) -> IngestedRun:
    """Ingest every synthetic document once in one run."""
    paths = [synthetic_documents[name] for name in UPLOAD_ORDER]
    return ingest_files(tmp_path_factory.mktemp("storage"), "run_0001", paths, bundle)


def test_word_chunk_ids_kinds_and_sections(ingested: IngestedRun) -> None:
    """Word paragraphs are grouped by heading path; the table is a table_rows chunk."""
    chunks = chunks_of(ingested.result, "doc01")
    assert [(chunk.chunk_id, chunk.kind) for chunk in chunks] == [
        ("doc01-c001", "paragraph"),
        ("doc01-c002", "paragraph"),
        ("doc01-c003", "table_rows"),
        ("doc01-c004", "paragraph"),
        ("doc01-c005", "paragraph"),
    ]
    assert chunks[2].section == "Synthetic Method SYN-001 > 6 Materials > 6.2 Reagents"
    assert chunks[4].section == "Synthetic Method SYN-001 > 6 Materials > 6.3 Handling"
    assert all(chunk.page is None and chunk.sheet is None for chunk in chunks)


def test_reagent_table_stays_in_one_chunk(ingested: IngestedRun) -> None:
    """Every row of the reagent table, header included, is in the one table chunk."""
    table_chunk = chunks_of(ingested.result, "doc01")[2]
    assert table_chunk.text is not None
    lines = table_chunk.text.split("\n")
    assert lines == [" | ".join(row) for row in files.REAGENT_TABLE]


def test_very_large_word_table_is_split_with_the_header_repeated(ingested: IngestedRun) -> None:
    """A table over the row limit becomes several chunks, each starting with the header row."""
    chunks = chunks_of(ingested.result, "doc02")
    header = " | ".join(files.REAGENT_TABLE[0])
    assert len(chunks) == 3
    assert all(chunk.kind == "table_rows" for chunk in chunks)
    assert all((chunk.text or "").split("\n")[0] == header for chunk in chunks)
    data_rows = sum(len((chunk.text or "").split("\n")) - 1 for chunk in chunks)
    assert data_rows == files.LARGE_ROW_COUNT


def test_pdf_text_pages_become_one_chunk_per_page(ingested: IngestedRun) -> None:
    """Each PDF page with text is one chunk carrying its page number."""
    chunks = chunks_of(ingested.result, "doc03")
    assert [(chunk.chunk_id, chunk.page, chunk.kind) for chunk in chunks] == [
        ("doc03-p01-c001", 1, "paragraph"),
        ("doc03-p02-c002", 2, "paragraph"),
    ]
    assert "page two" in (chunks[1].text or "")
    assert ingested.result.documents[2].page_count == 2


def test_scanned_page_becomes_an_image_chunk_without_text(ingested: IngestedRun) -> None:
    """A page with no text is a page_image chunk: no text, and a reference to its stored PNG."""
    [chunk] = chunks_of(ingested.result, "doc04")
    assert chunk.kind == "page_image"
    assert chunk.is_scanned
    assert chunk.text is None
    assert chunk.image_ref == "runs/run_0001/pages/doc04-p01-c001.png"
    image_path = ingested.folder.resolve_ref(chunk.image_ref)
    assert image_path.read_bytes().startswith(PNG_SIGNATURE)


def test_scanned_pages_give_a_run_issue(ingested: IngestedRun) -> None:
    """A PDF with scanned pages gets SCANNED_PAGES, naming the file and listing the pages."""
    [issue] = [issue for issue in ingested.result.issues if issue.code == "SCANNED_PAGES"]
    assert issue.record_id is None and issue.field is None
    assert issue.details == {"document_id": "doc04", "pages": [1]}
    assert files.SCANNED_PDF_FILE in issue.message


def test_xlsx_chunks_per_sheet_and_row_range(ingested: IngestedRun) -> None:
    """Each sheet is split by row range; IDs carry the sheet name and the rows."""
    chunks = chunks_of(ingested.result, "doc05")
    assert [chunk.chunk_id for chunk in chunks] == [
        "doc05-sReagents-r1-5",
        "doc05-sLargeSheet-r1-51",
        "doc05-sLargeSheet-r52-101",
        "doc05-sLargeSheet-r102-121",
    ]
    assert all(chunk.kind == "sheet_rows" for chunk in chunks)
    assert (chunks[1].sheet, chunks[1].row_range) == ("Large Sheet", "1-51")


def test_later_sheet_chunks_repeat_the_header_row(ingested: IngestedRun) -> None:
    """A split sheet repeats its header row at the top of every later chunk."""
    chunks = chunks_of(ingested.result, "doc05")
    header = " | ".join(files.REAGENT_TABLE[0])
    assert all((chunk.text or "").split("\n")[0] == header for chunk in chunks)
    assert (chunks[3].text or "").split("\n")[1].startswith("Synthetic Item 101 |")


def test_loader_file_is_skipped_with_a_run_issue(ingested: IngestedRun) -> None:
    """A workbook with the DFD columns as its header row is not read into chunks."""
    assert chunks_of(ingested.result, "doc06") == []
    assert ingested.result.documents[5].status == "loader_skipped"
    assert issue_codes(ingested.result)["doc06"] == "LOADER_FILE_UPLOADED"


def test_unreadable_file_is_skipped_with_a_run_issue(ingested: IngestedRun) -> None:
    """A file that cannot be read gets FILE_UNREADABLE and the run goes on."""
    assert chunks_of(ingested.result, "doc07") == []
    assert ingested.result.documents[6].status == "unreadable"
    assert issue_codes(ingested.result)["doc07"] == "FILE_UNREADABLE"
    assert ingested.result.readable_document_count() == 5


@pytest.mark.parametrize("file_name", ["synthetic_broken.pdf", "synthetic_broken.xlsx"])
def test_broken_pdf_and_workbook_are_unreadable(
    tmp_path: Path, bundle: ConfigBundle, file_name: str
) -> None:
    """A broken PDF or workbook is unreadable too; no readable document remains."""
    path = tmp_path / file_name
    path.write_bytes(b"synthetic: not a real file of this type")
    run = ingest_files(tmp_path / "storage", "run_0001", [path], bundle)
    assert [issue.code for issue in run.result.issues] == ["FILE_UNREADABLE"]
    assert run.result.readable_document_count() == 0


def test_ingest_writes_chunks_and_document_list(ingested: IngestedRun) -> None:
    """chunks.json holds every chunk; documents.json holds statuses and page counts."""
    assert ingested.folder.read_chunks() == ingested.result.chunks
    assert ingested.folder.read_documents() == ingested.result.documents


def test_document_list_holds_no_document_text(ingested: IngestedRun) -> None:
    """documents.json holds references and fingerprints only, never chunk text."""
    document_list = ingested.folder.documents_file.read_text(encoding="utf-8")
    for chunk in ingested.result.chunks:
        assert chunk.text is None or chunk.text not in document_list


def test_chunk_ids_are_the_same_on_reingest(
    ingested: IngestedRun,
    synthetic_documents: dict[str, Path],
    bundle: ConfigBundle,
    tmp_path: Path,
) -> None:
    """The same files in the same order give the same chunks, in a new run or the same one."""
    paths = [synthetic_documents[name] for name in UPLOAD_ORDER]
    again = ingest_files(tmp_path, "run_0001", paths, bundle)
    assert again.result.chunks == ingested.result.chunks
    assert ingest_run(again.folder, bundle).chunks == ingested.result.chunks


def test_missing_catalogue_code_is_a_config_error(
    tmp_path: Path, synthetic_documents: dict[str, Path], bundle: ConfigBundle
) -> None:
    """A run issue code missing from the catalogue stops ingest with a plain config error."""
    catalogue = bundle.issue_catalogue.model_copy(update={"run_issues": {}})
    broken_bundle = bundle.model_copy(update={"issue_catalogue": catalogue})
    with pytest.raises(ConfigError, match="FILE_UNREADABLE"):
        ingest_files(tmp_path, "run_0001", [synthetic_documents[files.BROKEN_FILE]], broken_bundle)
