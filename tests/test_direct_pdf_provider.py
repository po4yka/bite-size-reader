"""Unit tests for DirectPDFProvider."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.content.scraper.direct_pdf_provider import DirectPDFProvider, _is_pdf_url
from app.core.call_status import CallStatus

# ---------------------------------------------------------------------------
# _is_pdf_url helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://example.com/report.pdf", True),
        ("https://example.com/report.PDF", True),
        ("https://example.com/report.pdf?v=2", True),
        ("https://example.com/report.pdf#page=3", True),
        ("https://example.com/update-pdf-viewer", False),
        ("https://example.com/document", False),
        ("https://example.com/document.html", False),
        ("https://example.com/doc.pdf.zip", False),
    ],
)
def test_is_pdf_url(url: str, expected: bool) -> None:
    assert _is_pdf_url(url) == expected


# ---------------------------------------------------------------------------
# Provider behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_pdf_url_fast_fails() -> None:
    provider = DirectPDFProvider()
    result = await provider.scrape_markdown("https://example.com/article")
    assert result.status == CallStatus.ERROR
    assert "not a .pdf URL" in (result.error_text or "")


@pytest.mark.asyncio
async def test_pdf_url_extracted_successfully() -> None:
    fake_pdf = b"%PDF-1.4 fake pdf bytes"
    provider = DirectPDFProvider(min_text_length=5)

    with (
        patch.object(provider, "_fetch_pdf", new=AsyncMock(return_value=fake_pdf)),
        patch(
            "app.adapters.content.scraper.direct_pdf_provider._extract_text_sync",
            return_value="Extracted PDF text content here.",
        ),
    ):
        result = await provider.scrape_markdown("https://example.com/paper.pdf")

    assert result.status == CallStatus.OK
    assert result.content_markdown == "Extracted PDF text content here."


@pytest.mark.asyncio
async def test_fetch_returns_none_gives_error() -> None:
    provider = DirectPDFProvider()

    with patch.object(provider, "_fetch_pdf", new=AsyncMock(return_value=None)):
        result = await provider.scrape_markdown("https://example.com/file.pdf")

    assert result.status == CallStatus.ERROR
    assert "not a valid PDF" in (result.error_text or "")


@pytest.mark.asyncio
async def test_short_extraction_gives_error() -> None:
    provider = DirectPDFProvider(min_text_length=500)

    with (
        patch.object(provider, "_fetch_pdf", new=AsyncMock(return_value=b"%PDF- bytes")),
        patch(
            "app.adapters.content.scraper.direct_pdf_provider._extract_text_sync",
            return_value="short",
        ),
    ):
        result = await provider.scrape_markdown("https://example.com/tiny.pdf")

    assert result.status == CallStatus.ERROR
    assert "too short" in (result.error_text or "")


@pytest.mark.asyncio
async def test_fetch_exception_gives_error() -> None:
    provider = DirectPDFProvider()

    with patch.object(
        provider, "_fetch_pdf", new=AsyncMock(side_effect=OSError("connection refused"))
    ):
        result = await provider.scrape_markdown("https://example.com/broken.pdf")

    assert result.status == CallStatus.ERROR
    assert "connection refused" in (result.error_text or "")


def test_factory_registers_direct_pdf_when_fitz_available() -> None:
    pytest.importorskip("fitz", reason="PyMuPDF (fitz) required for direct_pdf provider")
    from app.adapters.content.scraper.factory import _build_direct_pdf

    cfg = MagicMock()
    cfg.direct_pdf_enabled = True
    cfg.profile = "balanced"
    cfg.direct_pdf_timeout_sec = 60
    cfg.direct_pdf_max_size_mb = 20
    cfg.min_content_length = 400

    provider = _build_direct_pdf(cfg)
    assert provider is not None
    assert provider.provider_name == "direct_pdf"


def test_factory_skips_direct_pdf_when_disabled() -> None:
    from app.adapters.content.scraper.factory import _build_direct_pdf

    cfg = MagicMock()
    cfg.direct_pdf_enabled = False

    provider = _build_direct_pdf(cfg)
    assert provider is None
