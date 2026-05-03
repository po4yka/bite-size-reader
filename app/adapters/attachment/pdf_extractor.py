"""PDF text extraction and page rendering for LLM analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

from app.adapters.attachment.image_extractor import ImageContent, ImageExtractor

logger = get_logger(__name__)


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
    figure_page_count: int = 0


class PDFExtractor:
    """Stateless utility for extracting text and images from PDF files."""

    @staticmethod
    def _extract_page_content(
        *,
        doc: Any,
        pages_to_process: int,
        sparse_threshold: int,
        min_image_dimension: int,
        image_max_dimension: int,
        vector_draw_threshold: int,
        on_progress: Callable[[str], Any] | None,
        fitz_module: Any,
    ) -> tuple[list[str], list[int], list[int], list[str], list[ImageContent]]:
        """Extract per-page text, sparse/figure-page indices, links, and embedded images."""
        text_parts: list[str] = []
        sparse_page_indices: list[int] = []
        figure_page_indices: list[int] = []
        links: list[str] = []
        embedded_images: list[ImageContent] = []
        seen_image_xrefs: set[int] = set()

        for page_idx in range(pages_to_process):
            if on_progress and page_idx % 10 == 0:
                on_progress(f"Extracting content: page {page_idx + 1}/{pages_to_process}...")

            page = doc[page_idx]
            blocks = page.get_text("blocks")
            blocks.sort(key=lambda b: (b[1], b[0]))
            page_text = "\n".join(b[4].strip() for b in blocks if b[4].strip())

            # Inline detected tables as Markdown so the LLM gets structured data
            try:
                finder = page.find_tables()
                for t_idx, table in enumerate(finder.tables, 1):
                    try:
                        md = table.to_markdown()
                        if md.strip():
                            sep = "\n\n" if page_text else ""
                            page_text = f"{page_text}{sep}[Table {t_idx}]\n{md}"
                    except AttributeError:
                        pass  # to_markdown() absent in this PyMuPDF build
            except Exception as exc:
                logger.warning(
                    "pdf_table_detection_failed",
                    extra={"page": page_idx, "error": str(exc)},
                )

            text_parts.append(page_text)

            for link in page.get_links():
                if "uri" in link:
                    links.append(link["uri"])

            page_has_raster = False
            for img in page.get_images():
                xref = img[0]
                width, height = img[2], img[3]
                if xref in seen_image_xrefs:
                    continue
                if width < min_image_dimension or height < min_image_dimension:
                    continue
                seen_image_xrefs.add(xref)
                page_has_raster = True

                try:
                    pix = fitz_module.Pixmap(doc, xref)
                    if pix.n - pix.alpha < 4:
                        pix = fitz_module.Pixmap(fitz_module.csRGB, pix)
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

            # Detect vector-drawn figures (charts, diagrams) on text-rich pages.
            # page.get_drawings() returns path/fill operations; a high count indicates
            # a chart drawn from PDF primitives rather than an embedded raster.
            page_has_vector_figure = False
            if not page_has_raster:
                try:
                    page_has_vector_figure = len(page.get_drawings()) >= vector_draw_threshold
                except Exception:
                    pass

            if len(page_text) < sparse_threshold:
                sparse_page_indices.append(page_idx)
            elif page_has_raster or page_has_vector_figure:
                # Text-rich page with a figure: needs vision rendering
                figure_page_indices.append(page_idx)

        return text_parts, sparse_page_indices, figure_page_indices, links, embedded_images

    @staticmethod
    def _render_sparse_pages(
        *,
        doc: Any,
        vision_pages: list[int],
        image_max_dimension: int,
        file_path: Path,
        on_progress: Callable[[str], Any] | None,
    ) -> list[ImageContent]:
        """Render sparse pages to PNG for vision models."""
        image_pages: list[ImageContent] = []
        for i, page_idx in enumerate(vision_pages):
            if on_progress:
                on_progress(f"Rendering page {i + 1}/{len(vision_pages)} for vision...")
            try:
                page = doc[page_idx]
                pix = page.get_pixmap(dpi=200)
                img_bytes = pix.tobytes("png")
                image_content = ImageExtractor.extract_from_bytes(
                    img_bytes, max_dimension=image_max_dimension
                )
                image_pages.append(image_content)
            except Exception as exc:
                logger.warning(
                    "pdf_page_render_failed",
                    extra={"page": page_idx, "error": str(exc), "file": str(file_path)},
                )
        return image_pages

    @staticmethod
    def extract(
        file_path: str | Path,
        *,
        max_pages: int = 50,
        sparse_threshold: int = 100,
        max_vision_pages: int = 8,
        image_max_dimension: int = 2048,
        min_image_dimension: int = 100,
        max_embedded_images: int = 8,
        vector_draw_threshold: int = 30,
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

            text_parts, sparse_page_indices, figure_page_indices, links, embedded_images = (
                PDFExtractor._extract_page_content(
                    doc=doc,
                    pages_to_process=pages_to_process,
                    sparse_threshold=sparse_threshold,
                    min_image_dimension=min_image_dimension,
                    image_max_dimension=image_max_dimension,
                    vector_draw_threshold=vector_draw_threshold,
                    on_progress=on_progress,
                    fitz_module=fitz,
                )
            )

            # Limit embedded images to top N largest by file size to avoid overloading context
            embedded_images.sort(key=lambda img: img.file_size_bytes, reverse=True)
            embedded_images = embedded_images[:max_embedded_images]

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

            # Sparse pages take priority; figure pages (vector charts, embedded rasters on
            # text-rich pages) fill remaining slots up to max_vision_pages.
            vision_pages = list(
                dict.fromkeys(sparse_page_indices + figure_page_indices)
            )[:max_vision_pages]
            figure_page_count = sum(1 for p in vision_pages if p in figure_page_indices)

            image_pages = PDFExtractor._render_sparse_pages(
                doc=doc,
                vision_pages=vision_pages,
                image_max_dimension=image_max_dimension,
                file_path=file_path,
                on_progress=on_progress,
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
                figure_page_count=figure_page_count,
            )
        finally:
            doc.close()
