"""Agent orchestrator for coordinating multi-agent workflows."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from app.agents.content_extraction_agent import ContentExtractionAgent
    from app.agents.summarization_agent import SummarizationAgent
    from app.agents.validation_agent import ValidationAgent

from app.agents.content_extraction_agent import ExtractionInput
from app.agents.summarization_agent import SummarizationInput

logger = logging.getLogger(__name__)


class PipelineStage(str, Enum):
    """Pipeline execution stages."""

    EXTRACTION = "extraction"
    SUMMARIZATION = "summarization"
    VALIDATION = "validation"
    COMPLETE = "complete"


class RetryStrategy(str, Enum):
    """Retry strategy types."""

    NONE = "none"
    FIXED = "fixed"
    EXPONENTIAL = "exponential"
    LINEAR = "linear"


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    max_attempts: int = 3
    initial_delay_ms: int = 1000
    max_delay_ms: int = 30000
    backoff_multiplier: float = 2.0


@dataclass
class PipelineProgress:
    """Progress update for streaming pipeline."""

    correlation_id: str
    stage: PipelineStage
    progress_percent: float
    message: str
    metadata: dict[str, Any] | None = None


@dataclass
class PipelineInput:
    """Input for the complete summarization pipeline."""

    url: str
    correlation_id: str
    language: str = "en"
    force_refresh: bool = False
    max_summary_retries: int = 3
    retry_config: RetryConfig | None = None
    enable_state_persistence: bool = False
    state_dir: Path | None = None


@dataclass
class BatchPipelineInput:
    """Input for batch processing multiple URLs."""

    urls: list[str]
    base_correlation_id: str
    language: str = "en"
    force_refresh: bool = False
    max_summary_retries: int = 3
    max_concurrent: int = 3
    retry_config: RetryConfig | None = None


@dataclass
class PipelineOutput:
    """Output from the complete summarization pipeline."""

    summary_json: dict[str, Any]
    normalized_url: str
    content_length: int
    extraction_metadata: dict[str, Any]
    summarization_attempts: int
    validation_warnings: list[str]


@dataclass
class BatchPipelineOutput:
    """Output from batch pipeline processing."""

    correlation_id: str
    url: str
    success: bool
    output: PipelineOutput | None = None
    error: str | None = None
    attempts: int = 1


@dataclass
class PipelineState:
    """Saved state for pipeline resumption."""

    correlation_id: str
    url: str
    language: str
    stage: PipelineStage
    extraction_output: dict[str, Any] | None = None
    summarization_output: dict[str, Any] | None = None
    attempts: int = 1
    errors: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PipelineState:
        """Create from dictionary."""
        # Convert stage string to enum
        if "stage" in data and isinstance(data["stage"], str):
            data["stage"] = PipelineStage(data["stage"])
        return cls(**data)

    def save(self, state_dir: Path) -> None:
        """Save state to file."""
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file = state_dir / f"{self.correlation_id}.json"
        with state_file.open("w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        logger.info(f"Saved pipeline state to {state_file}")

    @classmethod
    def load(cls, correlation_id: str, state_dir: Path) -> PipelineState | None:
        """Load state from file."""
        state_file = state_dir / f"{correlation_id}.json"
        if not state_file.exists():
            return None
        with state_file.open() as f:
            data = json.load(f)
        logger.info(f"Loaded pipeline state from {state_file}")
        return cls.from_dict(data)


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
            ExtractionInput(
                url=input_data.url,
                correlation_id=correlation_id,
                force_refresh=input_data.force_refresh,
            )
        )

        if not extraction_result.success:
            self.logger.error(
                f"[Orchestrator] Extraction failed: {extraction_result.error}",
                extra={"correlation_id": correlation_id},
            )
            raise Exception(f"Content extraction failed: {extraction_result.error}") from None

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
            SummarizationInput(
                content=extracted_output.content_markdown,
                metadata=extracted_output.metadata,
                correlation_id=correlation_id,
                language=input_data.language,
                max_retries=input_data.max_summary_retries,
            )
        )

        if not summarization_result.success:
            self.logger.error(
                f"[Orchestrator] Summarization failed: {summarization_result.error}",
                extra={"correlation_id": correlation_id},
            )
            raise Exception(f"Summarization failed: {summarization_result.error}") from None

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
            "[Orchestrator] Pipeline completed successfully",
            extra={"correlation_id": correlation_id},
        )

        return {
            "success": True,
            "output": pipeline_output,
            "metadata": {
                "extraction_metadata": extraction_result.metadata,
                "summarization_metadata": summarization_result.metadata,
            },
        }

    async def execute_pipeline_streaming(
        self, input_data: PipelineInput
    ) -> AsyncIterator[PipelineProgress | dict[str, Any]]:
        """Execute pipeline with streaming progress updates.

        Yields progress updates during execution, then final result.

        Args:
            input_data: Pipeline parameters

        Yields:
            PipelineProgress objects during execution, final result dict at end
        """
        correlation_id = input_data.correlation_id

        # Initialize state if persistence enabled
        state: PipelineState | None = None
        if input_data.enable_state_persistence and input_data.state_dir:
            state = PipelineState.load(correlation_id, input_data.state_dir)
            if state:
                logger.info(f"Resuming pipeline from stage: {state.stage}")
                yield PipelineProgress(
                    correlation_id=correlation_id,
                    stage=state.stage,
                    progress_percent=0,
                    message=f"Resuming from {state.stage.value} stage",
                )

        # Phase 1: Extraction
        if not state or state.stage == PipelineStage.EXTRACTION:
            yield PipelineProgress(
                correlation_id=correlation_id,
                stage=PipelineStage.EXTRACTION,
                progress_percent=10,
                message="Starting content extraction",
            )

            extraction_result = await self.extraction_agent.execute(
                ExtractionInput(
                    url=input_data.url,
                    correlation_id=correlation_id,
                    force_refresh=input_data.force_refresh,
                )
            )

            if not extraction_result.success:
                yield {
                    "success": False,
                    "error": f"Extraction failed: {extraction_result.error}",
                    "stage": PipelineStage.EXTRACTION,
                }
                return

            yield PipelineProgress(
                correlation_id=correlation_id,
                stage=PipelineStage.EXTRACTION,
                progress_percent=40,
                message=f"Extracted {len(extraction_result.output.content_markdown)} chars",
                metadata={"content_length": len(extraction_result.output.content_markdown)},
            )

            # Save state if enabled
            if input_data.enable_state_persistence and input_data.state_dir:
                state = PipelineState(
                    correlation_id=correlation_id,
                    url=input_data.url,
                    language=input_data.language,
                    stage=PipelineStage.SUMMARIZATION,
                    extraction_output={
                        "content_markdown": extraction_result.output.content_markdown,
                        "metadata": extraction_result.output.metadata,
                    },
                )
                state.save(input_data.state_dir)

        # Phase 2: Summarization
        yield PipelineProgress(
            correlation_id=correlation_id,
            stage=PipelineStage.SUMMARIZATION,
            progress_percent=50,
            message="Generating summary",
        )

        summarization_result = await self.summarization_agent.execute(
            SummarizationInput(
                content=extraction_result.output.content_markdown,
                metadata=extraction_result.output.metadata,
                correlation_id=correlation_id,
                language=input_data.language,
                max_retries=input_data.max_summary_retries,
            )
        )

        if not summarization_result.success:
            yield {
                "success": False,
                "error": f"Summarization failed: {summarization_result.error}",
                "stage": PipelineStage.SUMMARIZATION,
            }
            return

        yield PipelineProgress(
            correlation_id=correlation_id,
            stage=PipelineStage.COMPLETE,
            progress_percent=100,
            message=f"Pipeline complete after {summarization_result.output.attempts} attempt(s)",
        )

        # Build final output
        pipeline_output = PipelineOutput(
            summary_json=summarization_result.output.summary_json,
            normalized_url=extraction_result.output.normalized_url,
            content_length=len(extraction_result.output.content_markdown),
            extraction_metadata=extraction_result.output.metadata,
            summarization_attempts=summarization_result.output.attempts,
            validation_warnings=summarization_result.output.corrections_applied,
        )

        # Clean up state file if persistence enabled
        if input_data.enable_state_persistence and input_data.state_dir:
            state_file = input_data.state_dir / f"{correlation_id}.json"
            if state_file.exists():
                state_file.unlink()
                logger.info(f"Removed completed state file: {state_file}")

        yield {"success": True, "output": pipeline_output}

    async def execute_batch_pipeline(
        self, input_data: BatchPipelineInput
    ) -> list[BatchPipelineOutput]:
        """Execute pipeline for multiple URLs in parallel.

        Args:
            input_data: Batch parameters including URLs and concurrency limit

        Returns:
            List of results for each URL
        """
        semaphore = asyncio.Semaphore(input_data.max_concurrent)

        async def process_url(url: str, index: int) -> BatchPipelineOutput:
            """Process a single URL with semaphore limiting."""
            async with semaphore:
                correlation_id = f"{input_data.base_correlation_id}-{index}"
                logger.info(f"[Batch] Processing URL {index + 1}: {url}")

                pipeline_input = PipelineInput(
                    url=url,
                    correlation_id=correlation_id,
                    language=input_data.language,
                    force_refresh=input_data.force_refresh,
                    max_summary_retries=input_data.max_summary_retries,
                    retry_config=input_data.retry_config,
                )

                try:
                    result = await self._execute_with_retry(pipeline_input)
                    # Extract actual attempt count from pipeline output
                    output = result.get("output")
                    attempts = output.summarization_attempts if output else 1
                    return BatchPipelineOutput(
                        correlation_id=correlation_id,
                        url=url,
                        success=result["success"],
                        output=output,
                        attempts=attempts,
                    )
                except Exception as e:
                    logger.error(f"[Batch] Failed to process {url}: {e}")
                    # For failures, we don't know the exact attempts, use 1 as fallback
                    return BatchPipelineOutput(
                        correlation_id=correlation_id,
                        url=url,
                        success=False,
                        error=str(e),
                        attempts=1,
                    )

        # Process all URLs concurrently (limited by semaphore)
        tasks = [process_url(url, i) for i, url in enumerate(input_data.urls)]
        results = await asyncio.gather(*tasks)

        # Log batch summary
        successful = sum(1 for r in results if r.success)
        logger.info(
            f"[Batch] Completed {len(results)} URLs: {successful} successful, "
            f"{len(results) - successful} failed"
        )

        return list(results)

    async def _execute_with_retry(self, input_data: PipelineInput) -> dict[str, Any]:
        """Execute pipeline with configurable retry strategy.

        Args:
            input_data: Pipeline parameters including retry config

        Returns:
            Pipeline result

        Raises:
            Exception: If all retry attempts fail
        """
        retry_config = input_data.retry_config or RetryConfig()
        last_error = None

        for attempt in range(1, retry_config.max_attempts + 1):
            try:
                logger.info(
                    f"[Retry] Attempt {attempt}/{retry_config.max_attempts}",
                    extra={"correlation_id": input_data.correlation_id},
                )

                result = await self.execute_pipeline(input_data)
                if result["success"]:
                    return result

                # Pipeline returned failure
                last_error = result.get("error", "Unknown error")

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"[Retry] Attempt {attempt} failed: {e}",
                    extra={"correlation_id": input_data.correlation_id},
                )

            # Calculate delay for next attempt
            if attempt < retry_config.max_attempts:
                delay_ms = self._calculate_retry_delay(attempt, retry_config.strategy, retry_config)
                delay_sec = min(delay_ms / 1000.0, retry_config.max_delay_ms / 1000.0)
                logger.info(
                    f"[Retry] Waiting {delay_sec:.1f}s before attempt {attempt + 1}",
                    extra={"correlation_id": input_data.correlation_id},
                )
                await asyncio.sleep(delay_sec)

        # All attempts exhausted
        error_msg = f"Pipeline failed after {retry_config.max_attempts} attempts: {last_error}"
        logger.error(error_msg, extra={"correlation_id": input_data.correlation_id})
        raise Exception(error_msg) from None

    def _calculate_retry_delay(
        self, attempt: int, strategy: RetryStrategy, config: RetryConfig
    ) -> float:
        """Calculate delay in milliseconds for retry attempt.

        Args:
            attempt: Current attempt number (1-indexed)
            strategy: Retry strategy to use
            config: Retry configuration

        Returns:
            Delay in milliseconds
        """
        if strategy == RetryStrategy.NONE:
            return 0

        if strategy == RetryStrategy.FIXED:
            return config.initial_delay_ms

        if strategy == RetryStrategy.LINEAR:
            return config.initial_delay_ms * attempt

        if strategy == RetryStrategy.EXPONENTIAL:
            return config.initial_delay_ms * (config.backoff_multiplier ** (attempt - 1))

        return config.initial_delay_ms


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

        return {
            "success": result.success,
            "output": result.output,
            "error": result.error,
            "metadata": result.metadata,
        }
