"""Office / EPUB / HTML document extraction via markitdown."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__)


@dataclass(frozen=True)
class DocumentContent:
    """Extracted document content as Markdown text."""

    text: str
    file_format: str
    truncated: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class MarkitdownExtractor:
    """Stateless utility for converting office documents to Markdown via markitdown."""

    @staticmethod
    def extract(
        file_path: str | Path,
        *,
        file_format: str,
        max_chars: int = 45_000,
        on_progress: Callable[[str], Any] | None = None,
    ) -> DocumentContent:
        """Convert a document file to Markdown text.

        Args:
            file_path: Path to the document file.
            file_format: Format hint (docx, pptx, xlsx, epub, rtf, csv, html, json, xml).
            max_chars: Truncate extracted text to this many characters.
            on_progress: Optional callback for progress updates.

        Returns:
            DocumentContent with extracted Markdown text.

        Raises:
            ValueError: If markitdown is not installed, the file is missing, or conversion fails.
        """
        try:
            from markitdown import MarkItDown
        except ModuleNotFoundError as exc:
            msg = (
                "Document processing requires the markitdown package. "
                "Install with: pip install 'markitdown[docx,pptx,xlsx,outlook]'"
            )
            raise ValueError(msg) from exc

        file_path = Path(file_path)
        if not file_path.exists():
            msg = f"Document file not found: {file_path}"
            raise ValueError(msg)

        if on_progress:
            on_progress(f"Converting {file_format} document...")

        try:
            md = MarkItDown()
            result = md.convert_local(str(file_path))
            text = result.text_content or ""
        except Exception as exc:
            logger.warning(
                "markitdown_conversion_failed",
                extra={"file_format": file_format, "error": str(exc)},
            )
            msg = f"Could not convert {file_format} document: {exc}"
            raise ValueError(msg) from exc

        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars]

        logger.debug(
            "markitdown_extracted",
            extra={
                "file_format": file_format,
                "chars": len(text),
                "truncated": truncated,
            },
        )

        return DocumentContent(
            text=text,
            file_format=file_format,
            truncated=truncated,
        )
