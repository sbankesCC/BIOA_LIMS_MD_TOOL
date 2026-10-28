"""Run store tests: folder layout, uploads with SHA-256, refused files, chunks and references."""

import hashlib
from pathlib import Path

import pytest

from app.contracts.chunk import Chunk
from app.ingest.file_types import RejectedFileError
from app.storage.run_store import RunFolder, RunStore, RunStoreError

SYNTHETIC_CONTENT = b"synthetic upload content"


def make_chunk(chunk_id: str) -> Chunk:
    """Return a small synthetic text chunk."""
    return Chunk(
        chunk_id=chunk_id,
        document_id="doc01",
        page=None,
        section=None,
        sheet=None,
        row_range=None,
        kind="paragraph",
        is_scanned=False,
        text="synthetic text",
        image_ref=None,
    )


@pytest.fixture
def folder(tmp_path: Path) -> RunFolder:
    """Create a new run folder in a temp storage folder."""
    return RunStore(tmp_path).create_run("run_0001")


def test_new_run_has_the_folder_layout(folder: RunFolder, tmp_path: Path) -> None:
    """A new run gets uploads, pages, llm and exports folders and an empty document list."""
    run_path = tmp_path / "runs" / "run_0001"
    for name in ("uploads", "pages", "llm", "exports"):
        assert (run_path / name).is_dir()
    assert folder.read_documents() == []


def test_upload_is_stored_with_its_sha256(folder: RunFolder) -> None:
    """The upload is written unchanged and its SHA-256 and size are recorded."""
    document = folder.save_upload("synthetic_method.docx", SYNTHETIC_CONTENT)
    assert folder.upload_path(document).read_bytes() == SYNTHETIC_CONTENT
    assert document.sha256 == hashlib.sha256(SYNTHETIC_CONTENT).hexdigest()
    assert document.size_bytes == len(SYNTHETIC_CONTENT)
    assert document.file_type == "docx"
    assert document.upload_ref == "runs/run_0001/uploads/doc01/synthetic_method.docx"
    assert folder.read_documents() == [document]


def test_documents_are_numbered_in_upload_order(folder: RunFolder) -> None:
    """Document IDs are doc01, doc02, ... in upload order."""
    first = folder.save_upload("synthetic_a.pdf", SYNTHETIC_CONTENT)
    second = folder.save_upload("synthetic_b.xlsx", SYNTHETIC_CONTENT)
    assert [first.document_id, second.document_id] == ["doc01", "doc02"]


def test_two_uploads_with_the_same_name_do_not_clash(folder: RunFolder) -> None:
    """Each document has its own folder, so a repeated file name keeps both files."""
    first = folder.save_upload("synthetic.pdf", b"synthetic one")
    second = folder.save_upload("synthetic.pdf", b"synthetic two")
    assert folder.upload_path(first).read_bytes() == b"synthetic one"
    assert folder.upload_path(second).read_bytes() == b"synthetic two"


@pytest.mark.parametrize(
    "file_name",
    ["synthetic.xls", "synthetic.xlsm", "synthetic.doc", "synthetic.txt", "synthetic"],
)
def test_rejected_extensions_are_refused_and_not_stored(folder: RunFolder, file_name: str) -> None:
    """Only .docx, .pdf and .xlsx are accepted; a refused file is never written."""
    with pytest.raises(RejectedFileError, match="Upload only"):
        folder.save_upload(file_name, SYNTHETIC_CONTENT)
    assert folder.read_documents() == []
    assert list(folder.uploads_dir.iterdir()) == []


def test_extension_check_ignores_case(folder: RunFolder) -> None:
    """An upper-case extension is accepted."""
    assert folder.save_upload("SYNTHETIC.PDF", SYNTHETIC_CONTENT).file_type == "pdf"


@pytest.mark.parametrize("file_name", ["../synthetic.pdf", "folder\\synthetic.pdf", " "])
def test_file_name_with_folder_parts_is_refused(folder: RunFolder, file_name: str) -> None:
    """A name with folder parts could escape the uploads folder, so it is refused."""
    with pytest.raises(RejectedFileError, match="not a valid file name"):
        folder.save_upload(file_name, SYNTHETIC_CONTENT)


@pytest.mark.parametrize("run_id", ["../run_0001", "0001", "run_00/1", ""])
def test_invalid_run_id_is_refused(tmp_path: Path, run_id: str) -> None:
    """Run IDs become folder names, so only plain run_... IDs are accepted."""
    with pytest.raises(RunStoreError, match="not a valid run ID"):
        RunStore(tmp_path).create_run(run_id)


def test_existing_run_cannot_be_created_again(folder: RunFolder, tmp_path: Path) -> None:
    """Creating a run that already exists is refused, so no files are overwritten."""
    with pytest.raises(RunStoreError, match="already exists"):
        RunStore(tmp_path).create_run(folder.run_id)


def test_missing_run_cannot_be_opened(tmp_path: Path) -> None:
    """Opening a run that does not exist gives a plain error."""
    with pytest.raises(RunStoreError, match="was not found"):
        RunStore(tmp_path).open_run("run_9999")


def test_open_run_finds_an_existing_run(folder: RunFolder, tmp_path: Path) -> None:
    """An existing run opens with the same folder."""
    assert RunStore(tmp_path).open_run(folder.run_id).path == folder.path


def test_chunks_round_trip(folder: RunFolder) -> None:
    """Chunks written to chunks.json read back unchanged and can be found by ID."""
    chunks = [make_chunk("doc01-c001"), make_chunk("doc01-c002")]
    folder.write_chunks(chunks)
    assert folder.read_chunks() == chunks
    assert folder.find_chunk("doc01-c002") == chunks[1]


def test_unknown_chunk_is_a_plain_error(folder: RunFolder) -> None:
    """Looking up a chunk ID the run does not have names the chunk."""
    folder.write_chunks([make_chunk("doc01-c001")])
    with pytest.raises(RunStoreError, match="doc01-c009 is not in run"):
        folder.find_chunk("doc01-c009")


def test_reading_chunks_before_ingest_is_a_plain_error(folder: RunFolder) -> None:
    """A run without chunks.json says ingest has not finished."""
    with pytest.raises(RunStoreError, match="no chunks yet"):
        folder.read_chunks()


def test_repeated_chunk_ids_are_refused(folder: RunFolder) -> None:
    """Chunk IDs must be unique within a run."""
    with pytest.raises(RunStoreError, match="repeated chunk IDs"):
        folder.write_chunks([make_chunk("doc01-c001"), make_chunk("doc01-c001")])


def test_page_image_is_stored_under_pages(folder: RunFolder) -> None:
    """A page image is saved under pages/ and its reference resolves back to the file."""
    image_ref = folder.save_page_image("doc01-p01-c001", b"synthetic png bytes")
    assert image_ref == "runs/run_0001/pages/doc01-p01-c001.png"
    assert folder.resolve_ref(image_ref).read_bytes() == b"synthetic png bytes"


def test_reference_outside_storage_is_refused(folder: RunFolder) -> None:
    """A reference that climbs out of STORAGE_DIR is refused."""
    with pytest.raises(RunStoreError, match="outside the storage folder"):
        folder.resolve_ref("../outside.txt")
