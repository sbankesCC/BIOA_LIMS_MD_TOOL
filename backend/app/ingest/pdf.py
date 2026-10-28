"""PDF reader: one text chunk per page; a page with no text (scanned) becomes a `page_image` chunk.

Scanned pages are rendered to PNG and stored in the run store; the chunk holds only a reference.
There is no OCR.
"""

import io
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pypdfium2  # pyright: ignore[reportMissingTypeStubs]
from PIL import Image

from app.contracts.chunk import Chunk
from app.ingest.chunking import ChunkIdCounter

# Rendering scale for scanned pages: 2 means 144 dots per inch (PDF pages are 72 per inch)
RENDER_SCALE = 2

# Stores a page PNG under a chunk ID and returns its run-store reference
SavePageImage = Callable[[str, bytes], str]


@dataclass
class PdfContent:
    """What a PDF gave: its chunks, its page count and the numbers of its scanned pages."""

    chunks: list[Chunk] = field(default_factory=list[Chunk])
    page_count: int = 0
    scanned_pages: list[int] = field(default_factory=list[int])


def read_pdf_chunks(path: Path, document_id: str, save_page_image: SavePageImage) -> PdfContent:
    """Read a PDF page by page into text chunks, or image chunks for pages without text."""
    content = PdfContent()
    chunk_ids = ChunkIdCounter(document_id)
    pdf = pypdfium2.PdfDocument(path)
    try:
        content.page_count = len(pdf)
        for index in range(content.page_count):
            page_number = index + 1
            chunk_id = chunk_ids.next_id(page=page_number)
            page = pdf[index]
            text = read_page_text(page)
            # A page with no text at all is a scanned page: keep it as an image
            if text.strip():
                content.chunks.append(make_text_chunk(chunk_id, document_id, page_number, text))
            else:
                image_ref = save_page_image(chunk_id, render_page_png(page))
                content.chunks.append(
                    make_image_chunk(chunk_id, document_id, page_number, image_ref)
                )
                content.scanned_pages.append(page_number)
    finally:
        pdf.close()
    return content


def read_page_text(page: pypdfium2.PdfPage) -> str:
    """Return a page's text with plain line breaks."""
    text_page = page.get_textpage()
    try:
        text = text_page.get_text_range()
    finally:
        text_page.close()
    return text.replace("\r\n", "\n").replace("\r", "\n")


def render_page_png(page: pypdfium2.PdfPage) -> bytes:
    """Render a page to PNG bytes."""
    # pypdfium2 has no type information, so the bitmap is untyped until it becomes a PIL image
    untyped_page = cast(Any, page)
    image = cast(Image.Image, untyped_page.render(scale=RENDER_SCALE).to_pil())
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def make_text_chunk(chunk_id: str, document_id: str, page: int, text: str) -> Chunk:
    """Build the text chunk for one PDF page."""
    return Chunk(
        chunk_id=chunk_id,
        document_id=document_id,
        page=page,
        section=None,
        sheet=None,
        row_range=None,
        kind="paragraph",
        is_scanned=False,
        text=text,
        image_ref=None,
    )


def make_image_chunk(chunk_id: str, document_id: str, page: int, image_ref: str) -> Chunk:
    """Build the `page_image` chunk for one scanned PDF page: no text, only the image reference."""
    return Chunk(
        chunk_id=chunk_id,
        document_id=document_id,
        page=page,
        section=None,
        sheet=None,
        row_range=None,
        kind="page_image",
        is_scanned=True,
        text=None,
        image_ref=image_ref,
    )
