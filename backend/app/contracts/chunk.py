"""Chunk (CONTRACTS §1): a labeled piece of a source document that the model sees and cites."""

from typing import Literal

from app.contracts.base import ContractModel

ChunkKind = Literal["paragraph", "table_rows", "sheet_rows", "page_image"]


class Chunk(ContractModel):
    """One chunk; a `page_image` chunk has no text and points to its PNG in the run store."""

    chunk_id: str
    document_id: str
    page: int | None
    section: str | None
    sheet: str | None
    row_range: str | None
    kind: ChunkKind
    is_scanned: bool
    text: str | None
    image_ref: str | None
