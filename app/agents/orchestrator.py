"""Agent orchestrator for coordinating multi-agent workflows."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.agents.content_extraction_agent import ContentExtractionAgent
    from app.agents.summarization_agent import SummarizationAgent
    from app.agents.validation_agent import ValidationAgent

logger = logging.getLogger(__name__)


@dataclass
class PipelineInput:
    """Input for the complete summarization pipeline."""

    url: str
    correlation_id: str
    language: str = "en"
    force_refresh: bool = False
    max_summary_retries: int = 3


@dataclass
class PipelineOutput:
    """Output from the complete summarization pipeline."""

    summary_json: dict[str, Any]
    normalized_url: str
    content_length: int
    extraction_metadata: dict[str, Any]
    summarization_attempts: int
    validation_warnings: list[str]


class AgentOrchestrator:
    """Orchestrates multi-agent workflow for content summarization.

    The orchestrator coordinates three specialized agents:
    1. ContentExtractionAgent - Extracts content from URLs
    2. SummarizationAgent - Generates summaries with feedback loop
    3. ValidationAgent - Validates summary contract compliance

    Flow:
        URL → Extract → Validate Content → Summarize ← Validate → Retry if needed → Output
    """

    def __init__(
        self,
        extraction_agent: ContentExtractionAgent,
        summarization_agent: SummarizationAgent,
        validation_agent: ValidationAgent,
    ):
        """Initialize the orchestrator.

        Args:
            extraction_agent: Agent for content extraction
            summarization_agent: Agent for summarization
            validation_agent: Agent for validation
        """
        self.extraction_agent = extraction_agent
        self.summarization_agent = summarization_agent
        self.validation_agent = validation_agent
        self.logger = logger

    async def execute_pipeline(self, input_data: PipelineInput) -> dict[str, Any]:
        """Execute the complete multi-agent summarization pipeline.

        Args:
            input_data: Pipeline parameters including URL and options

        Returns:
            Result dictionary with summary or error information

        Raises:
            Exception: If pipeline execution fails
        """
        correlation_id = input_data.correlation_id

        self.logger.info(
            f"[Orchestrator] Starting pipeline for URL: {input_data.url}",
            extra={"correlation_id": correlation_id},
        )

        # Phase 1: Content Extraction
        self.logger.info(
            "[Orchestrator] Phase 1: Content Extraction", extra={"correlation_id": correlation_id}
        )

        extraction_result = await self.extraction_agent.execute(
            {
                "url": input_data.url,
                "correlation_id": correlation_id,
                "force_refresh": input_data.force_refresh,
            }
        )

        if not extraction_result.success:
            self.logger.error(
                f"[Orchestrator] Extraction failed: {extraction_result.error}",
                extra={"correlation_id": correlation_id},
            )
            raise Exception(f"Content extraction failed: {extraction_result.error}")

        extracted_output = extraction_result.output
        self.logger.info(
            f"[Orchestrator] Extraction successful - {len(extracted_output.content_markdown)} chars",
            extra={"correlation_id": correlation_id},
        )

        # Phase 2: Summarization with Validation Feedback Loop
        self.logger.info(
            "[Orchestrator] Phase 2: Summarization with Feedback Loop",
            extra={"correlation_id": correlation_id},
        )

        summarization_result = await self.summarization_agent.execute(
            {
                "content": extracted_output.content_markdown,
                "metadata": extracted_output.metadata,
                "correlation_id": correlation_id,
                "language": input_data.language,
                "max_retries": input_data.max_summary_retries,
            }
        )

        if not summarization_result.success:
            self.logger.error(
                f"[Orchestrator] Summarization failed: {summarization_result.error}",
                extra={"correlation_id": correlation_id},
            )
            raise Exception(f"Summarization failed: {summarization_result.error}")

        summary_output = summarization_result.output
        self.logger.info(
            f"[Orchestrator] Summarization successful after {summary_output.attempts} attempt(s)",
            extra={"correlation_id": correlation_id},
        )

        # Build final output
        pipeline_output = PipelineOutput(
            summary_json=summary_output.summary_json,
            normalized_url=extracted_output.normalized_url,
            content_length=len(extracted_output.content_markdown),
            extraction_metadata=extracted_output.metadata,
            summarization_attempts=summary_output.attempts,
            validation_warnings=summary_output.corrections_applied,
        )

        self.logger.info(
            "[Orchestrator] Pipeline completed successfully", extra={"correlation_id": correlation_id}
        )

        return {
            "success": True,
            "output": pipeline_output,
            "metadata": {
                "extraction_metadata": extraction_result.metadata,
                "summarization_metadata": summarization_result.metadata,
            },
        }


class SingleAgentOrchestrator:
    """Simpler orchestrator for single-agent workflows.

    Use this when you need to execute a single agent in isolation
    rather than the full multi-agent pipeline.
    """

    def __init__(self, agent: Any):
        """Initialize with a single agent.

        Args:
            agent: The agent to orchestrate
        """
        self.agent = agent
        self.logger = logger

    async def execute(self, input_data: Any, correlation_id: str) -> dict[str, Any]:
        """Execute a single agent.

        Args:
            input_data: Input for the agent
            correlation_id: Correlation ID for tracing

        Returns:
            Result dictionary
        """
        self.logger.info(
            f"[SingleAgentOrchestrator] Executing {self.agent.name}",
            extra={"correlation_id": correlation_id},
        )

        result = await self.agent.execute(input_data)

        if result.success:
            self.logger.info(
                f"[SingleAgentOrchestrator] {self.agent.name} succeeded",
                extra={"correlation_id": correlation_id},
            )
        else:
            self.logger.error(
                f"[SingleAgentOrchestrator] {self.agent.name} failed: {result.error}",
                extra={"correlation_id": correlation_id},
            )

        return {"success": result.success, "output": result.output, "error": result.error, "metadata": result.metadata}
