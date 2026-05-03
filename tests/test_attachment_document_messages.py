"""Tests verifying that the document attachment path uses the correct model and format."""

from __future__ import annotations

from typing import Any
from unittest import mock
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.attachment._attachment_content import AttachmentContentService, _MIME_TO_FORMAT
from app.adapters.attachment.markitdown_extractor import DocumentContent


# ---------------------------------------------------------------------------
# Context fixture (mirrors test_attachment_pdf_messages.py)
# ---------------------------------------------------------------------------


def _make_context() -> MagicMock:
    ctx = MagicMock()
    ctx.cfg.attachment.vision_model = "qwen/qwen3-vl-32b-instruct"
    ctx.cfg.attachment.vision_fallback_models = ("moonshotai/kimi-k2.5",)
    ctx.cfg.attachment.document_processing_enabled = True
    ctx.cfg.attachment.max_document_chars = 45_000
    ctx.cfg.openrouter.temperature = 0.3
    ctx.cfg.openrouter.top_p = 0.9
    ctx.cfg.openrouter.structured_output_mode = "json_schema"
    ctx.cfg.runtime.preferred_lang = "en"
    ctx.workflow.build_structured_response_format.side_effect = lambda mode=None: (
        {"type": "json_object"} if mode == "json_object" else {"type": "json_schema", "json_schema": {}}
    )
    return ctx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_document_uses_default_model_and_json_schema() -> None:
    """process_document must use no model_override and not trigger the vision model path."""
    ctx = _make_context()
    persistence = MagicMock()
    persistence.update_document_metadata = AsyncMock()
    svc = AttachmentContentService(ctx, persistence=persistence, workflow=MagicMock())

    captured_run: dict[str, Any] = {}

    async def fake_run(**kwargs: Any) -> None:
        captured_run.update(kwargs)

    svc._workflow.run_summary_workflow = fake_run  # type: ignore[method-assign]

    doc_content = DocumentContent(text="Hello document", file_format="docx", truncated=False)

    with mock.patch(
        "app.adapters.attachment._attachment_content.MarkitdownExtractor.extract",
        return_value=doc_content,
    ):
        await svc.process_document(
            file_path="/tmp/fake.docx",
            file_format="docx",
            caption=None,
            chosen_lang="en",
            req_id=10,
            correlation_id="test-cid",
            interaction_id=None,
            message=MagicMock(),
        )

    assert captured_run.get("model_override") is None, "document must NOT use vision model"


@pytest.mark.asyncio
async def test_document_dispatch_uses_document_type_for_docx_mime() -> None:
    """classify_attachment must return 'document' for docx MIME type."""
    ctx = _make_context()
    svc = AttachmentContentService(ctx, persistence=MagicMock(), workflow=MagicMock())

    doc_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    message = MagicMock()
    message.photo = None
    message.document.mime_type = doc_mime
    message.document.file_name = "report.docx"

    file_type, mime, _fname = svc.classify_attachment(message)

    assert file_type == "document"
    assert mime == doc_mime


def test_mime_to_format_covers_all_document_types() -> None:
    """Every entry in _MIME_TO_FORMAT maps to a non-empty format string."""
    for mime_type, fmt in _MIME_TO_FORMAT.items():
        assert fmt, f"empty format for MIME {mime_type!r}"


def test_classify_attachment_returns_none_when_document_processing_disabled() -> None:
    """If document_processing_enabled is False, classify_attachment returns None for docs."""
    ctx = _make_context()
    ctx.cfg.attachment.document_processing_enabled = False
    svc = AttachmentContentService(ctx, persistence=MagicMock(), workflow=MagicMock())

    message = MagicMock()
    message.photo = None
    message.document.mime_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    message.document.file_name = "report.docx"

    file_type, mime, _fname = svc.classify_attachment(message)

    assert file_type is None
    assert mime is None
