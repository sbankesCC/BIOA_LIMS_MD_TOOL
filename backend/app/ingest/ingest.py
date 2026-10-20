"""Ingest a run: read every uploaded document into chunks and report run issues.

Writes `chunks.json` and the updated `documents.json` to the run store. The result holds chunk
text; the graph keeps only document and chunk references from it (CONTRACTS §7).
"""

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import JsonValue

from app.config.bundle import ConfigBundle
from app.config.errors import ConfigError
from app.config.issue_catalogue import IssueCatalogue, fill_message
from app.contracts.chunk import Chunk
from app.contracts.issue import Issue
from app.ids import make_issue_id
from app.ingest.docx import read_docx_chunks
from app.ingest.loader_detection import is_loader_workbook
from app.ingest.pdf import read_pdf_chunks
from app.ingest.xlsx import make_sheet_chunks, read_workbook_sheets
from app.storage.run_store import DocumentInfo, DocumentStatus, RunFolder

# Run issue codes raised by ingest (defined in the client's issue catalogue)
FILE_UNREADABLE = "FILE_UNREADABLE"
SCANNED_PAGES = "SCANNED_PAGES"
LOADER_FILE_UPLOADED = "LOADER_FILE_UPLOADED"


@dataclass
class IssueNote:
    """A run issue found while reading one document, before it becomes an Issue."""

    code: str
    details: dict[str, JsonValue] = field(default_factory=dict[str, JsonValue])


@dataclass
class DocumentOutcome:
    """What reading one document gave: its new status, page count, chunks and issue notes."""

    status: DocumentStatus
    chunks: list[Chunk] = field(default_factory=list[Chunk])
    page_count: int | None = None
    notes: list[IssueNote] = field(default_factory=list[IssueNote])


@dataclass
class IngestResult:
    """The run's documents (with status), all chunks in upload order, and run issues."""

    documents: list[DocumentInfo]
    chunks: list[Chunk]
    issues: list[Issue]

    def readable_document_count(self) -> int:
        """Return how many documents were read into chunks (unreadable and loaders excluded)."""
        return sum(1 for document in self.documents if document.status == "ingested")


def ingest_run(folder: RunFolder, bundle: ConfigBundle) -> IngestResult:
    """Read every uploaded document of a run, store the chunks and return them with run issues."""
    result = IngestResult(documents=[], chunks=[], issues=[])
    for document in folder.read_documents():
        outcome = ingest_document(folder, document, bundle.dfd_template.headers)
        updated = document.model_copy(
            update={"status": outcome.status, "page_count": outcome.page_count}
        )
        result.documents.append(updated)
        result.chunks.extend(outcome.chunks)
        for note in outcome.notes:
            result.issues.append(make_run_issue(bundle.issue_catalogue, note, updated))
    # Chunks first: the document list then shows a finished ingest
    folder.write_chunks(result.chunks)
    folder.write_documents(result.documents)
    return result


def ingest_document(
    folder: RunFolder, document: DocumentInfo, dfd_headers: list[str]
) -> DocumentOutcome:
    """Read one document; a file that cannot be read is skipped with FILE_UNREADABLE."""
    path = folder.upload_path(document)
    try:
        return read_document(folder, document, path, dfd_headers)
    except Exception:
        # The readers raise many kinds of errors for a broken, encrypted or mislabeled file;
        # any of them means the file is unreadable, and the run goes on with the other files
        return DocumentOutcome(status="unreadable", notes=[IssueNote(FILE_UNREADABLE)])


def read_document(
    folder: RunFolder, document: DocumentInfo, path: Path, dfd_headers: list[str]
) -> DocumentOutcome:
    """Pick the reader for the document's type and return what it read."""
    if document.file_type == "docx":
        return DocumentOutcome(
            status="ingested", chunks=read_docx_chunks(path, document.document_id)
        )
    if document.file_type == "pdf":
        return read_pdf_document(folder, document, path)
    return read_xlsx_document(document, path, dfd_headers)


def read_pdf_document(folder: RunFolder, document: DocumentInfo, path: Path) -> DocumentOutcome:
    """Read a PDF; scanned pages give one SCANNED_PAGES issue listing their page numbers."""
    content = read_pdf_chunks(path, document.document_id, folder.save_page_image)
    outcome = DocumentOutcome(
        status="ingested", chunks=content.chunks, page_count=content.page_count
    )
    if content.scanned_pages:
        pages: list[JsonValue] = list(content.scanned_pages)
        outcome.notes.append(IssueNote(SCANNED_PAGES, {"pages": pages}))
    return outcome


def read_xlsx_document(
    document: DocumentInfo, path: Path, dfd_headers: list[str]
) -> DocumentOutcome:
    """Read a workbook; a DFD loader or earlier export is skipped with LOADER_FILE_UPLOADED."""
    sheets = read_workbook_sheets(path)
    if is_loader_workbook(sheets, dfd_headers):
        return DocumentOutcome(status="loader_skipped", notes=[IssueNote(LOADER_FILE_UPLOADED)])
    return DocumentOutcome(
        status="ingested", chunks=make_sheet_chunks(sheets, document.document_id)
    )


def make_run_issue(catalogue: IssueCatalogue, note: IssueNote, document: DocumentInfo) -> Issue:
    """Build a run issue for one document from the catalogue's severity and message."""
    definition = catalogue.run_issues.get(note.code)
    if definition is None:
        raise ConfigError(
            [f"issue_catalogue.yaml: run issue {note.code}, used by ingest, is missing."]
        )
    return Issue(
        # The document ID keys the issue, so two files with the same name get separate issues
        issue_id=make_issue_id(note.code, None, None, document.document_id),
        code=note.code,
        severity=definition.severity,
        record_id=None,
        field=None,
        message=fill_message(definition.message, {"file": document.file_name}),
        individual_review=definition.individual_review,
        details={"document_id": document.document_id, **note.details},
    )
