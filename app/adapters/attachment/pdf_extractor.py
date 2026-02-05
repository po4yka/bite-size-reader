"""PDF text extraction and page rendering for LLM analysis."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF

from app.adapters.attachment.image_extractor import ImageContent, ImageExtractor

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PDFContent:
    """Extracted PDF content with text and optional rendered page images."""

    text: str
    page_count: int
    image_pages: list[ImageContent] = field(default_factory=list)
    is_scanned: bool = False
    truncated: bool = False


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
    ) -> PDFContent:
        """Extract text and optionally render sparse/scanned pages from a PDF.

        Args:
            file_path: Path to the PDF file.
            max_pages: Maximum number of pages to process.
            sparse_threshold: Pages with fewer characters than this are considered sparse/scanned.
            max_vision_pages: Maximum number of sparse pages to render as images for vision LLM.
            image_max_dimension: Maximum dimension for rendered page images.

        Returns:
            PDFContent with extracted text and optional page images.

        Raises:
            ValueError: If the PDF is encrypted, invalid, or cannot be opened.
        """
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

            text_parts: list[str] = []
            sparse_page_indices: list[int] = []

            # Pass 1: Extract text and identify sparse pages
            for page_idx in range(pages_to_process):
                page = doc[page_idx]
                page_text = page.get_text().strip()
                text_parts.append(page_text)

                if len(page_text) < sparse_threshold:
                    sparse_page_indices.append(page_idx)

            full_text = "\n\n".join(
                f"--- Page {i + 1} ---\n{text}" for i, text in enumerate(text_parts) if text
            )

            # Determine if the PDF is predominantly scanned/image-based
            is_scanned = len(sparse_page_indices) > pages_to_process * 0.5

            # Pass 2: Render sparse pages as images for vision LLM
            image_pages: list[ImageContent] = []
            vision_pages = sparse_page_indices[:max_vision_pages]

            for page_idx in vision_pages:
                try:
                    page = doc[page_idx]
                    # Render at 150 DPI for balance between quality and size
                    pix = page.get_pixmap(dpi=150)
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
                is_scanned=is_scanned,
                truncated=truncated,
            )
        finally:
            doc.close()
