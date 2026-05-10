"""Shared state TypedDict for the LangGraph summarization pipeline."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class SummarizationGraphState(TypedDict):
    """State threaded through every node of the summarization graph.

    Fields with ``Annotated[list[str], operator.add]`` are accumulator fields:
    LangGraph merges node return values by concatenating lists rather than
    replacing them, so errors and corrections from every attempt are preserved.
    """

    # ── immutable inputs ──────────────────────────────────────────────────────
    content: str
    metadata: dict[str, Any]
    language: str
    correlation_id: str
    max_retries: int

    # ── accumulated across retries ────────────────────────────────────────────
    validation_errors: Annotated[list[str], operator.add]
    corrections_applied: Annotated[list[str], operator.add]
    response_hashes: Annotated[list[str], operator.add]

    # ── mutable per-attempt state ─────────────────────────────────────────────
    summary_json: dict[str, Any] | None
    llm_call_id: int | None
    attempt: int
    validation_passed: bool
    feedback_ignored: bool

    # ── web search enrichment (populated by web_search node when present) ─────
    web_search_context: str
