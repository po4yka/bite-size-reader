"""LangGraph node factory functions for the summarization pipeline.

Each ``make_*_node`` function is a closure that captures a service/agent
instance and returns an ``async def`` node compatible with LangGraph's
``StateGraph``. No langgraph imports at module level — nodes are plain
async functions; langgraph only sees them as callables.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

from app.agents.langgraph.state import SummarizationGraphState
from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from app.adapters.content.pure_summary_service import PureSummaryService
    from app.agents.validation_agent import ValidationAgent, ValidationInput
    from app.agents.web_search_agent import WebSearchAgent, WebSearchAgentInput

logger = get_logger(__name__)


# ── web search ────────────────────────────────────────────────────────────────

def make_web_search_node(web_search_agent: WebSearchAgent):  # type: ignore[type-arg]
    """Return a node that runs web search enrichment before summarization."""

    async def web_search_node(state: SummarizationGraphState) -> dict[str, Any]:
        from app.agents.web_search_agent import WebSearchAgentInput

        result = await web_search_agent.execute(
            WebSearchAgentInput(
                content=state["content"],
                language=state["language"],
                correlation_id=state["correlation_id"],
            )
        )
        if result.success and result.output and result.output.searched:
            return {"web_search_context": result.output.context}
        return {"web_search_context": ""}

    return web_search_node


# ── summarize ─────────────────────────────────────────────────────────────────

def make_summarize_node(pure_summary_service: PureSummaryService):  # type: ignore[type-arg]
    """Return a node that calls the LLM and tracks duplicate responses."""

    async def summarize_node(state: SummarizationGraphState) -> dict[str, Any]:
        from app.adapters.content.summarization_models import PureSummaryRequest
        from app.prompts.manager import get_prompt_manager

        # Load system prompt
        try:
            manager = get_prompt_manager()
            system_prompt = manager.get_system_prompt(
                state["language"], include_examples=True, num_examples=2
            )
        except Exception:
            system_prompt = (
                "You are a precise assistant that returns only a strict JSON object "
                "matching the provided schema."
            )

        # Build correction feedback from all accumulated errors
        feedback_instructions: str | None = None
        if state["validation_errors"]:
            feedback_instructions = _build_correction_prompt(state["validation_errors"])

        # Prepend web search context to content when available
        content = state["content"]
        if state.get("web_search_context"):
            content = (
                f"{content}\n\n---WEB SEARCH CONTEXT---\n{state['web_search_context']}"
            )

        result = await pure_summary_service.summarize(
            PureSummaryRequest(
                content_text=content,
                chosen_lang=state["language"],
                system_prompt=system_prompt,
                correlation_id=state["correlation_id"],
                feedback_instructions=feedback_instructions,
            )
        )

        new_attempt = state["attempt"] + 1

        if result is None:
            return {
                "attempt": new_attempt,
                "summary_json": None,
                "validation_passed": False,
            }

        response_hash = _hash_response(result)
        updates: dict[str, Any] = {
            "summary_json": result,
            "attempt": new_attempt,
            "response_hashes": [response_hash],
            "llm_call_id": result.get("llm_call_id"),
            "validation_passed": False,
        }

        # Detect if LLM is ignoring feedback (hash seen 2+ times already → 3rd occurrence)
        if state["response_hashes"].count(response_hash) >= 2:
            updates["feedback_ignored"] = True
            logger.warning(
                "[SummarizationGraph] LLM returned identical response 3 times — aborting",
                extra={"correlation_id": state["correlation_id"]},
            )

        return updates

    return summarize_node


# ── validate ──────────────────────────────────────────────────────────────────

def make_validate_node(validation_agent: ValidationAgent):  # type: ignore[type-arg]
    """Return a node that validates the current summary_json against contract."""

    async def validate_node(state: SummarizationGraphState) -> dict[str, Any]:
        from app.agents.validation_agent import ValidationInput

        if state["summary_json"] is None:
            error = f"Attempt {state['attempt']}: LLM returned no result"
            return {
                "validation_errors": [error],
                "corrections_applied": [error],
                "validation_passed": False,
            }

        result = await validation_agent.execute(
            ValidationInput(summary_json=state["summary_json"])
        )

        if result.success and result.output:
            return {
                "summary_json": result.output.summary_json,
                "corrections_applied": result.output.corrections_applied,
                "validation_passed": True,
            }

        error_msg = result.error or "Unknown validation error"
        attempt_label = f"Attempt {state['attempt']}: {error_msg}"
        return {
            "validation_errors": [attempt_label],
            "corrections_applied": [attempt_label],
            "validation_passed": False,
        }

    return validate_node


# ── helpers ───────────────────────────────────────────────────────────────────

def _hash_response(response: dict[str, Any]) -> str:
    try:
        normalized = json.dumps(response, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    except Exception:
        return hashlib.sha256(str(id(response)).encode()).hexdigest()


def _build_correction_prompt(errors: list[str]) -> str:
    """Build a structured correction prompt from accumulated validation errors."""
    if not errors:
        return ""

    char_errors = [e for e in errors if "chars" in e.lower() or "character" in e.lower()]
    tag_errors = [e for e in errors if "tag" in e.lower() or "#" in e]
    field_errors = [e for e in errors if "missing" in e.lower() or "required" in e.lower()]
    json_errors = [e for e in errors if "json" in e.lower()]
    other_errors = [
        e
        for e in errors
        if e not in char_errors
        and e not in tag_errors
        and e not in field_errors
        and e not in json_errors
    ]

    prompt = "\n\nCORRECTIONS NEEDED FROM PREVIOUS ATTEMPT:\n"

    if char_errors:
        prompt += "\nCharacter Limits:\n"
        prompt += "".join(f"  - {e}\n" for e in char_errors)
        prompt += (
            "  FIX: summary_250 must be a single sentence under 250 chars. "
            "summary_1000 must be 3-5 sentences under 1000 chars.\n"
        )
    if tag_errors:
        prompt += "\nTopic Tags:\n"
        prompt += "".join(f"  - {e}\n" for e in tag_errors)
        prompt += "  FIX: Each tag must start with #, e.g. #machine-learning\n"
    if field_errors:
        prompt += "\nRequired Fields:\n"
        prompt += "".join(f"  - {e}\n" for e in field_errors)
        prompt += "  FIX: Include all required fields with non-empty values.\n"
    if json_errors:
        prompt += "\nJSON Structure:\n"
        prompt += "".join(f"  - {e}\n" for e in json_errors)
        prompt += "  FIX: Output ONLY a valid JSON object. No prose, no code fences.\n"
    if other_errors:
        prompt += "\nOther Issues:\n"
        prompt += "".join(f"  - {e}\n" for e in other_errors)

    prompt += "\nGenerate a corrected summary that addresses ALL issues above.\n"
    return prompt
