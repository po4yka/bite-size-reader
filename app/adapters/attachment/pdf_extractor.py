"""PDF text extraction and page rendering for LLM analysis."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from app.adapters.attachment.image_extractor import ImageContent, ImageExtractor

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PDFContent:
    """Extracted PDF content with text and optional rendered page images."""

    text: str
    page_count: int
    image_pages: list[ImageContent] = field(default_factory=list)
    embedded_images: list[ImageContent] = field(default_factory=list)
    is_scanned: bool = False
    truncated: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    toc: list[list[Any]] = field(default_factory=list)


class PDFExtractor:
    """Stateless utility for extracting text and images from PDF files."""

    @staticmethod
    def extract(
        file_path: str | Path,
        *,
        max_pages: int = 50,
        sparse_threshold: int = 100,
        max_vision_pages: int = 5,
        image_max_dimension: int = 2048,
        min_image_dimension: int = 200,
        on_progress: Callable[[str], Any] | None = None,
    ) -> PDFContent:
        """Extract text and optionally render sparse/scanned pages from a PDF.

        Args:
            file_path: Path to the PDF file.
            max_pages: Maximum number of pages to process.
            sparse_threshold: Pages with fewer characters than this are considered sparse/scanned.
            max_vision_pages: Maximum number of sparse pages to render as images for vision LLM.
            image_max_dimension: Maximum dimension for rendered page images.
            on_progress: Optional callback for progress updates.

        Returns:
            PDFContent with extracted text and optional page images.

        Raises:
            ValueError: If the PDF is encrypted, invalid, or cannot be opened.
        """
        try:
            import fitz  # PyMuPDF
        except ModuleNotFoundError as exc:
            msg = (
                "PDF processing requires PyMuPDF (`fitz`). "
                "Install dependencies with the `pymupdf` package."
            )
            raise ValueError(msg) from exc

        file_path = Path(file_path)
        if not file_path.exists():
            msg = f"PDF file not found: {file_path}"
            raise ValueError(msg)

        try:
            doc = fitz.open(str(file_path))
        except Exception as exc:
            msg = f"Cannot open PDF file: {exc}"
            raise ValueError(msg) from exc

        try:
            if doc.is_encrypted:
                msg = "Cannot process password-protected PDFs"
                raise ValueError(msg)

            total_pages = len(doc)
            pages_to_process = min(total_pages, max_pages)
            truncated = total_pages > max_pages
            metadata = doc.metadata or {}
            toc = doc.get_toc() or []

            if on_progress:
                on_progress(f"Reading {pages_to_process} pages...")

            text_parts: list[str] = []
            sparse_page_indices: list[int] = []
            links: list[str] = []
            embedded_images: list[ImageContent] = []
            seen_image_xrefs = set()

            # Pass 1: Extract text, links, and identify sparse pages
            for page_idx in range(pages_to_process):
                if on_progress and page_idx % 10 == 0:
                    on_progress(f"Extracting content: page {page_idx + 1}/{pages_to_process}...")

                page = doc[page_idx]
                # Use block-based extraction for better layout preservation
                blocks = page.get_text("blocks")
                # Sort blocks by vertical then horizontal position
                blocks.sort(key=lambda b: (b[1], b[0]))

                page_text_parts = []
                for b in blocks:
                    block_text = b[4].strip()
                    if block_text:
                        page_text_parts.append(block_text)

                page_text = "\n".join(page_text_parts)
                text_parts.append(page_text)

                # Collect links
                for link in page.get_links():
                    if "uri" in link:
                        links.append(link["uri"])

                # Extract embedded images
                for img in page.get_images():
                    xref = img[0]
                    width, height = img[2], img[3]

                    if xref in seen_image_xrefs:
                        continue
                    if width < min_image_dimension or height < min_image_dimension:
                        continue

                    seen_image_xrefs.add(xref)

                    try:
                        # Extract and convert image
                        pix = fitz.Pixmap(doc, xref)

                        # Handle CMYK/alpha mismatch
                        if pix.n - pix.alpha < 4:
                            # Convert to RGB
                            pix = fitz.Pixmap(fitz.csRGB, pix)

                        img_bytes = pix.tobytes("png")

                        image_content = ImageExtractor.extract_from_bytes(
                            img_bytes, max_dimension=image_max_dimension
                        )
                        embedded_images.append(image_content)

                    except Exception as exc:
                        logger.warning(
                            "pdf_embedded_image_extract_failed",
                            extra={"xref": xref, "error": str(exc)},
                        )

                if len(page_text) < sparse_threshold:
                    sparse_page_indices.append(page_idx)

            # Limit embedded images to top 5 largest by file size to avoid overloading context
            embedded_images.sort(key=lambda img: img.file_size_bytes, reverse=True)
            embedded_images = embedded_images[:5]

            # De-duplicate links while preserving order
            unique_links: list[str] = []
            seen_links = set()
            for link_uri in links:
                if link_uri not in seen_links:
                    seen_links.add(link_uri)
                    unique_links.append(link_uri)

            full_text = "\n\n".join(
                f"--- Page {i + 1} ---\n{text}" for i, text in enumerate(text_parts) if text
            )

            if unique_links:
                full_text += "\n\n--- Extracted Links ---\n" + "\n".join(unique_links[:20])

            # Determine if the PDF is predominantly scanned/image-based
            is_scanned = len(sparse_page_indices) > pages_to_process * 0.5

            # Pass 2: Render sparse pages as images for vision LLM
            image_pages: list[ImageContent] = []
            vision_pages = sparse_page_indices[:max_vision_pages]

            for i, page_idx in enumerate(vision_pages):
                if on_progress:
                    on_progress(f"Rendering page {i + 1}/{len(vision_pages)} for vision...")
                try:
                    page = doc[page_idx]
                    # Render at 200 DPI for better quality (OCR-ready for Vision models)
                    pix = page.get_pixmap(dpi=200)
                    img_bytes = pix.tobytes("png")
                    image_content = ImageExtractor.extract_from_bytes(
                        img_bytes, max_dimension=image_max_dimension
                    )
                    image_pages.append(image_content)
                except Exception as exc:
                    logger.warning(
                        "pdf_page_render_failed",
                        extra={
                            "page": page_idx,
                            "error": str(exc),
                            "file": str(file_path),
                        },
                    )

            if truncated:
                logger.info(
                    "pdf_truncated",
                    extra={
                        "total_pages": total_pages,
                        "processed_pages": pages_to_process,
                        "file": str(file_path),
                    },
                )

            return PDFContent(
                text=full_text,
                page_count=total_pages,
                image_pages=image_pages,
                embedded_images=embedded_images,
                is_scanned=is_scanned,
                truncated=truncated,
                metadata=metadata,
                toc=toc,
            )
        finally:
            doc.close()
