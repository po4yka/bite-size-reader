"""Deprecated compatibility export for adapter-level LLM request/response models."""

from __future__ import annotations

from app.adapter_models.llm.llm_models import ChatRequest, LLMCallResult

__all__ = ["ChatRequest", "LLMCallResult"]
