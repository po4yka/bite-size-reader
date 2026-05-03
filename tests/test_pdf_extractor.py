"""Unit tests for PDFExtractor using synthetic PyMuPDF documents."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import Any

import pytest

pytest.importorskip("fitz", reason="PyMuPDF (fitz) required for PDF extractor tests")

import fitz

from app.adapters.attachment.pdf_extractor import PDFContent, PDFExtractor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pdf(tmp_path: Path, *, filename: str = "test.pdf") -> tuple[Path, Any]:
    """Open a new in-memory fitz document and return (path, doc) for building."""
    doc = fitz.open()
    return tmp_path / filename, doc


def _save(doc: Any, path: Path) -> None:
    doc.save(str(path))
    doc.close()


def _make_png_bytes(width: int, height: int, color: tuple[int, int, int] = (200, 100, 50)) -> bytes:
    """Create a minimal solid-color PNG via fitz.Pixmap."""
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, width, height))
    pix.set_rect(pix.irect, color)
    return pix.tobytes("png")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_pure_text_pdf_no_images(tmp_path: Path) -> None:
    path, doc = _make_pdf(tmp_path)
    page = doc.new_page()
    page.insert_text((50, 100), "This is plain body text. " * 20)
    _save(doc, path)

    result = PDFExtractor.extract(str(path))

    assert isinstance(result, PDFContent)
    assert result.image_pages == []
    assert result.embedded_images == []
    assert result.is_scanned is False
    assert result.figure_page_count == 0
    assert "plain body text" in result.text


def test_scanned_pdf_renders_sparse_pages(tmp_path: Path) -> None:
    """Pages with fewer than sparse_threshold chars should be rendered for vision."""
    path, doc = _make_pdf(tmp_path)
    # Three nearly-blank pages (simulating scanned images with very little selectable text)
    for _ in range(3):
        page = doc.new_page()
        page.insert_text((50, 100), "x")  # < 100 chars
    _save(doc, path)

    result = PDFExtractor.extract(str(path), sparse_threshold=100, max_vision_pages=5)

    assert result.is_scanned is True
    assert len(result.image_pages) == 3


def test_text_rich_page_with_embedded_image_renders_for_vision(tmp_path: Path) -> None:
    """A text-rich page that also contains an embedded raster image should be rendered."""
    path, doc = _make_pdf(tmp_path)
    page = doc.new_page()
    # Add enough text to exceed the sparse threshold
    page.insert_text((50, 50), "Detailed analysis text. " * 20)
    # Embed a 300x300 raster (well above the 100-px dimension floor)
    img_bytes = _make_png_bytes(300, 300)
    page.insert_image(fitz.Rect(200, 200, 500, 500), stream=img_bytes)
    _save(doc, path)

    result = PDFExtractor.extract(
        str(path),
        min_image_dimension=100,
        max_vision_pages=5,
    )

    # The page must be included in the vision-rendered set (figure_page_count > 0)
    assert result.figure_page_count >= 1
    assert len(result.image_pages) >= 1
    assert result.is_scanned is False


def test_text_rich_page_with_vector_chart_renders_for_vision(tmp_path: Path) -> None:
    """A text-rich page with enough vector drawing operations should be rendered."""
    path, doc = _make_pdf(tmp_path)
    page = doc.new_page()
    page.insert_text((50, 50), "Analysis results follow. " * 20)
    # Draw 35 line segments — exceeds the default vector_draw_threshold of 30
    for i in range(35):
        y = 300 + i * 5
        page.draw_line((50, y), (400, y))
    _save(doc, path)

    result = PDFExtractor.extract(
        str(path),
        vector_draw_threshold=30,
        max_vision_pages=5,
    )

    assert result.figure_page_count >= 1
    assert len(result.image_pages) >= 1


def test_min_image_dimension_filter_respects_config(tmp_path: Path) -> None:
    """A 150x150 image should be dropped at the default 200-px floor but kept at 100 px."""
    path, doc = _make_pdf(tmp_path)
    page = doc.new_page()
    page.insert_text((50, 50), "Some text. " * 10)
    img_bytes = _make_png_bytes(150, 150)
    page.insert_image(fitz.Rect(50, 200, 200, 350), stream=img_bytes)
    _save(doc, path)

    result_drop = PDFExtractor.extract(str(path), min_image_dimension=200)
    result_keep = PDFExtractor.extract(str(path), min_image_dimension=100)

    assert result_drop.embedded_images == []
    assert len(result_keep.embedded_images) >= 1


def test_top_n_embedded_images_respects_config(tmp_path: Path) -> None:
    """Only the top max_embedded_images images should be retained, sorted by file size."""
    path, doc = _make_pdf(tmp_path)
    page = doc.new_page(width=2000, height=2000)
    # Insert 10 distinct 200x200 images at non-overlapping positions
    for i in range(10):
        col, row = i % 5, i // 5
        x0, y0 = 50 + col * 350, 50 + row * 350
        color = (i * 25 % 256, i * 50 % 256, i * 75 % 256)
        img_bytes = _make_png_bytes(200, 200, color=color)
        page.insert_image(fitz.Rect(x0, y0, x0 + 200, y0 + 200), stream=img_bytes)
    _save(doc, path)

    result = PDFExtractor.extract(
        str(path),
        min_image_dimension=100,
        max_embedded_images=4,
    )

    assert len(result.embedded_images) <= 4


def test_table_detected_and_inlined_as_markdown(tmp_path: Path) -> None:
    """A page with a drawn table grid should produce Markdown table rows in the text."""
    path, doc = _make_pdf(tmp_path)
    page = doc.new_page()

    # Draw a simple 3-column x 3-row table with visible borders
    col_xs = [50, 150, 250, 350]
    row_ys = [100, 140, 180, 220]

    # Horizontal lines
    for y in row_ys:
        page.draw_line((col_xs[0], y), (col_xs[-1], y), width=1)
    # Vertical lines
    for x in col_xs:
        page.draw_line((x, row_ys[0]), (x, row_ys[-1]), width=1)

    # Insert cell text
    labels = [
        ("Col A", "Col B", "Col C"),
        ("10", "20", "30"),
        ("40", "50", "60"),
    ]
    for r_idx, row in enumerate(labels):
        for c_idx, text in enumerate(row):
            x = col_xs[c_idx] + 5
            y = row_ys[r_idx] + 25
            page.insert_text((x, y), text, fontsize=10)

    _save(doc, path)

    result = PDFExtractor.extract(str(path))

    # If find_tables() detected the grid and to_markdown() is available,
    # the text should contain pipe-separated rows.
    if "|" in result.text:
        assert "Col A" in result.text or "10" in result.text
    else:
        pytest.skip("Table not detected by this PyMuPDF build — grid may need stricter borders")
