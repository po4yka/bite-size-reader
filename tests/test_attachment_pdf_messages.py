"""Tests verifying that the vision/non-vision model path is chosen correctly for PDFs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.attachment._attachment_llm import AttachmentLLMWorkflowService
from app.adapters.attachment.pdf_extractor import PDFContent
from app.adapters.attachment.image_extractor import ImageContent


# ---------------------------------------------------------------------------
# Minimal ImageContent stub
# ---------------------------------------------------------------------------


def _make_image_content() -> ImageContent:
    return ImageContent(
        data_uri="data:image/png;base64,abc",
        mime_type="image/png",
        width=300,
        height=300,
        file_size_bytes=1024,
    )


# ---------------------------------------------------------------------------
# Context fixtures
# ---------------------------------------------------------------------------


def _make_context(vision_model: str = "qwen/qwen3-vl-32b-instruct") -> MagicMock:
    """Build a minimal AttachmentProcessorContext mock."""
    ctx = MagicMock()
    ctx.cfg.attachment.vision_model = vision_model
    ctx.cfg.attachment.vision_fallback_models = ("moonshotai/kimi-k2.5",)
    ctx.cfg.openrouter.temperature = 0.3
    ctx.cfg.openrouter.top_p = 0.9
    ctx.cfg.openrouter.structured_output_mode = "json_schema"
    ctx.workflow.build_structured_response_format.side_effect = lambda mode=None: (
        {"type": "json_object"} if mode == "json_object" else {"type": "json_schema", "json_schema": {}}
    )
    return ctx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pdf_with_images_uses_vision_model_and_json_object() -> None:
    """When a PDF has embedded images, run_summary_workflow must use the vision model
    and json_object response format (not json_schema strict)."""
    ctx = _make_context()
    svc = AttachmentLLMWorkflowService(ctx)

    captured: dict[str, Any] = {}

    async def fake_execute(**kwargs: Any) -> None:
        captured.update(kwargs)
        return None

    ctx.workflow.execute_summary_workflow = fake_execute

    await svc.run_summary_workflow(
        messages=[{"role": "user", "content": "test"}],
        req_id=1,
        correlation_id="abc",
        interaction_id=None,
        chosen_lang="en",
        message=MagicMock(),
        model_override="qwen/qwen3-vl-32b-instruct",
    )

    # execute_summary_workflow receives a `requests` list; inspect the first item
    requests_list = captured.get("requests", [])
    assert requests_list, "no LLMRequestConfig passed to execute_summary_workflow"
    first_req = requests_list[0]
    assert first_req.model_override == "qwen/qwen3-vl-32b-instruct"
    assert first_req.response_format == {"type": "json_object"}


@pytest.mark.asyncio
async def test_pdf_without_images_uses_default_model_and_json_schema() -> None:
    """When a PDF has no images, run_summary_workflow must use json_schema strict
    and must NOT set model_override."""
    ctx = _make_context()
    svc = AttachmentLLMWorkflowService(ctx)

    captured: dict[str, Any] = {}

    async def fake_execute(**kwargs: Any) -> None:
        captured.update(kwargs)
        return None

    ctx.workflow.execute_summary_workflow = fake_execute

    await svc.run_summary_workflow(
        messages=[{"role": "user", "content": "test"}],
        req_id=2,
        correlation_id="def",
        interaction_id=None,
        chosen_lang="en",
        message=MagicMock(),
        model_override=None,  # no images → no vision model
    )

    requests_list = captured.get("requests", [])
    assert requests_list, "no LLMRequestConfig passed to execute_summary_workflow"
    first_req = requests_list[0]
    assert not hasattr(first_req, "model_override") or first_req.model_override is None
    assert first_req.response_format == {"type": "json_schema", "json_schema": {}}
