"""Run store: the files of each run under `STORAGE_DIR/runs/<run_id>/`.

Layout: `uploads/<document_id>/<file name>`, `documents.json` (document list with SHA-256),
`chunks.json`, `pages/` (scanned page PNGs), `llm/` (LLM traces) and `exports/`.
References stored elsewhere (e.g. a chunk's `image_ref`) are paths relative to STORAGE_DIR.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, TypeAdapter

from app.contracts.chunk import Chunk
from app.ingest.file_types import FileType, read_file_type

RUNS_FOLDER = "runs"
UPLOADS_FOLDER = "uploads"
PAGES_FOLDER = "pages"
LLM_FOLDER = "llm"
EXPORTS_FOLDER = "exports"
DOCUMENTS_FILE = "documents.json"
CHUNKS_FILE = "chunks.json"

# Run IDs become folder names, so only plain characters are allowed
RUN_ID_PATTERN = re.compile(r"^run_[A-Za-z0-9_-]+$")

# Document IDs are numbered in upload order: doc01, doc02, ...
DOCUMENT_PREFIX = "doc"
DOCUMENT_NUMBER_WIDTH = 2

DocumentStatus = Literal["uploaded", "ingested", "unreadable", "loader_skipped"]


class RunStoreError(Exception):
    """Raised when the run store cannot do what was asked; the message says what to do."""


class DocumentInfo(BaseModel):
    """One uploaded document: name, type, fingerprint and ingest status (never its contents)."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    file_name: str
    file_type: FileType
    upload_ref: str
    sha256: str
    size_bytes: int
    page_count: int | None = None
    status: DocumentStatus = "uploaded"


DOCUMENT_LIST = TypeAdapter(list[DocumentInfo])
CHUNK_LIST = TypeAdapter(list[Chunk])


class RunStore:
    """The root of all run folders (STORAGE_DIR)."""

    def __init__(self, storage_dir: Path) -> None:
        """Remember the storage folder; nothing is created until a run is created."""
        self.storage_dir = storage_dir

    def create_run(self, run_id: str) -> "RunFolder":
        """Create the folder layout for a new run; refuse a run ID that already exists."""
        folder = RunFolder(self.storage_dir, run_id)
        if folder.path.exists():
            raise RunStoreError(f"Run {run_id} already exists. Start the run with a new ID.")
        folder.create_layout()
        return folder

    def open_run(self, run_id: str) -> "RunFolder":
        """Return the folder of an existing run; raise RunStoreError if there is none."""
        folder = RunFolder(self.storage_dir, run_id)
        if not folder.path.is_dir():
            raise RunStoreError(f"Run {run_id} was not found. Check the run ID.")
        return folder

    def resolve_ref(self, ref: str) -> Path:
        """Turn a stored reference into a path, refusing any that points outside STORAGE_DIR."""
        return resolve_inside(self.storage_dir, ref)


class RunFolder:
    """The files of one run: uploads, document list, chunks, page images, traces, exports."""

    def __init__(self, storage_dir: Path, run_id: str) -> None:
        """Point at `STORAGE_DIR/runs/<run_id>`; the run ID must be a plain `run_...` name."""
        if not RUN_ID_PATTERN.match(run_id):
            raise RunStoreError(f"'{run_id}' is not a valid run ID. Run IDs look like run_0001.")
        self.storage_dir = storage_dir
        self.run_id = run_id
        self.path = storage_dir / RUNS_FOLDER / run_id
        self.uploads_dir = self.path / UPLOADS_FOLDER
        self.pages_dir = self.path / PAGES_FOLDER
        self.llm_dir = self.path / LLM_FOLDER
        self.exports_dir = self.path / EXPORTS_FOLDER
        self.documents_file = self.path / DOCUMENTS_FILE
        self.chunks_file = self.path / CHUNKS_FILE

    def create_layout(self) -> None:
        """Create the run folder and its sub-folders, and an empty document list."""
        for folder in (self.uploads_dir, self.pages_dir, self.llm_dir, self.exports_dir):
            folder.mkdir(parents=True, exist_ok=True)
        self.write_documents([])

    def make_ref(self, path: Path) -> str:
        """Return a file's reference: its path relative to STORAGE_DIR, with forward slashes."""
        return path.relative_to(self.storage_dir).as_posix()

    def resolve_ref(self, ref: str) -> Path:
        """Turn a stored reference into a path, refusing any that points outside STORAGE_DIR."""
        return resolve_inside(self.storage_dir, ref)

    def save_upload(self, file_name: str, content: bytes) -> DocumentInfo:
        """Store an uploaded file with its SHA-256 and give it the next document ID."""
        # The type check comes first, so a refused file is never written
        file_type = read_file_type(file_name)
        documents = self.read_documents()
        document_id = format_document_id(len(documents) + 1)
        # Each document gets its own folder, so two uploads with the same name never clash
        target = self.uploads_dir / document_id / file_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        document = DocumentInfo(
            document_id=document_id,
            file_name=file_name,
            file_type=file_type,
            upload_ref=self.make_ref(target),
            sha256=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
        )
        self.write_documents([*documents, document])
        return document

    def upload_path(self, document: DocumentInfo) -> Path:
        """Return where a document's uploaded file is stored."""
        return self.resolve_ref(document.upload_ref)

    def read_documents(self) -> list[DocumentInfo]:
        """Return the run's document list (empty for a new run)."""
        if not self.documents_file.is_file():
            return []
        return DOCUMENT_LIST.validate_json(self.documents_file.read_bytes())

    def write_documents(self, documents: list[DocumentInfo]) -> None:
        """Replace the run's document list."""
        write_json(self.documents_file, DOCUMENT_LIST.dump_python(documents, mode="json"))

    def write_chunks(self, chunks: list[Chunk]) -> None:
        """Replace the run's chunks; chunk IDs must be unique."""
        chunk_ids = [chunk.chunk_id for chunk in chunks]
        if len(set(chunk_ids)) != len(chunk_ids):
            raise RunStoreError(f"Run {self.run_id} has repeated chunk IDs. Ingest the run again.")
        write_json(self.chunks_file, CHUNK_LIST.dump_python(chunks, mode="json"))

    def read_chunks(self) -> list[Chunk]:
        """Return the run's chunks; raise RunStoreError if ingest has not written them yet."""
        if not self.chunks_file.is_file():
            raise RunStoreError(f"Run {self.run_id} has no chunks yet. Wait for ingest to finish.")
        return CHUNK_LIST.validate_json(self.chunks_file.read_bytes())

    def find_chunk(self, chunk_id: str) -> Chunk:
        """Return one chunk by ID; raise RunStoreError if the run has no such chunk."""
        for chunk in self.read_chunks():
            if chunk.chunk_id == chunk_id:
                return chunk
        raise RunStoreError(f"Chunk {chunk_id} is not in run {self.run_id}. Check the chunk ID.")

    def save_page_image(self, chunk_id: str, png: bytes) -> str:
        """Store a scanned page's PNG under `pages/` and return its reference."""
        target = self.pages_dir / f"{chunk_id}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(png)
        return self.make_ref(target)


def format_document_id(number: int) -> str:
    """Format a document ID, e.g. 3 gives `doc03`."""
    return f"{DOCUMENT_PREFIX}{number:0{DOCUMENT_NUMBER_WIDTH}d}"


def resolve_inside(storage_dir: Path, ref: str) -> Path:
    """Return `storage_dir / ref`, refusing a reference that leaves the storage folder."""
    root = storage_dir.resolve()
    path = (root / ref).resolve()
    if not path.is_relative_to(root):
        raise RunStoreError(f"'{ref}' is outside the storage folder. Check the reference.")
    return path


def write_json(path: Path, data: object) -> None:
    """Write data as indented UTF-8 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
