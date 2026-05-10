"""LangGraph StateGraph for the summarization + validation + retry pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langgraph.graph import END, START, StateGraph

from app.agents.base_agent import AgentResult
from app.agents.langgraph.nodes import (
    make_summarize_node,
    make_validate_node,
    make_web_search_node,
)
from app.agents.langgraph.state import SummarizationGraphState
from app.agents.summarization_agent import SummarizationInput, SummarizationOutput
from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver

    from app.adapters.content.pure_summary_service import PureSummaryService
    from app.agents.validation_agent import ValidationAgent
    from app.agents.web_search_agent import WebSearchAgent

logger = get_logger(__name__)


# ── routing ───────────────────────────────────────────────────────────────────

def _route_after_validate(state: SummarizationGraphState) -> str:
    """Choose next node after validation completes."""
    if state.get("validation_passed"):
        return END
    if state.get("feedback_ignored"):
        return END
    if state["attempt"] >= state["max_retries"]:
        return END
    return "summarize"


# ── graph builder ─────────────────────────────────────────────────────────────

def build_summarization_graph(
    pure_summary_service: PureSummaryService,
    validation_agent: ValidationAgent,
    web_search_agent: WebSearchAgent | None = None,
) -> StateGraph:
    """Return a compiled-ready StateGraph for the summarize→validate→retry cycle."""
    builder: StateGraph = StateGraph(SummarizationGraphState)

    builder.add_node("summarize", make_summarize_node(pure_summary_service))
    builder.add_node("validate", make_validate_node(validation_agent))

    if web_search_agent is not None:
        builder.add_node("web_search", make_web_search_node(web_search_agent))
        builder.add_edge(START, "web_search")
        builder.add_edge("web_search", "summarize")
    else:
        builder.add_edge(START, "summarize")

    builder.add_edge("summarize", "validate")
    builder.add_conditional_edges("validate", _route_after_validate, ["summarize", END])

    return builder


# ── public facade ─────────────────────────────────────────────────────────────

class SummarizationGraph:
    """LangGraph-backed drop-in for SummarizationAgent's internal retry loop.

    Compiles a ``summarize → validate → [retry | done]`` StateGraph and exposes
    ``run()`` which accepts the same ``SummarizationInput`` the agent receives and
    returns the same ``AgentResult[SummarizationOutput]`` the agent returns, so
    existing callers (AgentOrchestrator) need no changes.
    """

    def __init__(
        self,
        pure_summary_service: PureSummaryService,
        validation_agent: ValidationAgent,
        web_search_agent: WebSearchAgent | None = None,
        checkpointer: BaseCheckpointSaver | None = None,
    ) -> None:
        graph = build_summarization_graph(pure_summary_service, validation_agent, web_search_agent)
        self._graph = graph.compile(checkpointer=checkpointer)

    async def run(self, input_data: SummarizationInput) -> AgentResult[SummarizationOutput]:
        """Execute the summarization graph and return an AgentResult."""
        initial_state: SummarizationGraphState = {
            "content": input_data.content,
            "metadata": input_data.metadata,
            "language": input_data.language,
            "correlation_id": input_data.correlation_id,
            "max_retries": input_data.max_retries,
            "validation_errors": [],
            "corrections_applied": [],
            "response_hashes": [],
            "summary_json": None,
            "llm_call_id": None,
            "attempt": 0,
            "validation_passed": False,
            "feedback_ignored": False,
            "web_search_context": "",
        }
        config: dict[str, Any] = {"configurable": {"thread_id": input_data.correlation_id}}

        try:
            final_state: SummarizationGraphState = await self._graph.ainvoke(
                initial_state, config=config
            )
        except Exception as exc:
            logger.error(
                "[SummarizationGraph] Graph invocation failed",
                extra={"correlation_id": input_data.correlation_id, "error": str(exc)},
            )
            return AgentResult.error_result(str(exc), attempts=0)

        summary_json = final_state.get("summary_json")
        attempts = final_state.get("attempt", 0)
        corrections = final_state.get("corrections_applied", [])

        if final_state.get("validation_passed") and summary_json:
            logger.info(
                f"[SummarizationGraph] Completed successfully after {attempts} attempt(s)",
                extra={"correlation_id": input_data.correlation_id},
            )
            return AgentResult.success_result(
                SummarizationOutput(
                    summary_json=summary_json,
                    llm_call_id=final_state.get("llm_call_id"),
                    attempts=attempts,
                    corrections_applied=corrections,
                ),
                attempts=attempts,
                had_corrections=bool(corrections),
            )

        if final_state.get("feedback_ignored"):
            error = "LLM repeatedly returned identical response — feedback ignored"
        elif corrections:
            error = f"Summarization failed after {attempts} attempt(s): {corrections[-1]}"
        else:
            error = "Summarization graph produced no valid output"

        logger.error(
            f"[SummarizationGraph] {error}",
            extra={"correlation_id": input_data.correlation_id},
        )
        return AgentResult.error_result(
            error,
            attempts=attempts,
            corrections_attempted=corrections,
            feedback_ignored=final_state.get("feedback_ignored", False),
        )
