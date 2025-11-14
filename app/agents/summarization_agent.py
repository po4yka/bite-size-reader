"""Summarization agent with self-correction feedback loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.agents.base_agent import AgentResult, BaseAgent

if TYPE_CHECKING:
    from app.adapters.content.llm_summarizer import LLMSummarizer


@dataclass
class SummarizationInput:
    """Input for summarization."""

    content: str
    metadata: dict[str, Any]
    correlation_id: str
    language: str = "en"
    max_retries: int = 3


@dataclass
class SummarizationOutput:
    """Output from summarization."""

    summary_json: dict[str, Any]
    llm_call_id: int | None
    attempts: int
    corrections_applied: list[str]


class SummarizationAgent(BaseAgent[SummarizationInput, SummarizationOutput]):
    """Agent responsible for LLM-based summarization with feedback loop.

    This agent:
    - Calls LLM to generate summaries
    - Validates summary output against contract
    - Implements self-correction feedback loop
    - Retries with refined prompts if validation fails
    - Tracks attempts and corrections for analysis
    """

    def __init__(
        self,
        llm_summarizer: LLMSummarizer,
        validator_agent: Any,  # Will be ValidationAgent
        correlation_id: str | None = None,
    ):
        """Initialize the summarization agent.

        Args:
            llm_summarizer: The LLM summarizer component
            validator_agent: Validation agent for checking outputs
            correlation_id: Optional correlation ID for tracing
        """
        super().__init__(name="SummarizationAgent", correlation_id=correlation_id)
        self.llm_summarizer = llm_summarizer
        self.validator_agent = validator_agent

    async def execute(
        self, input_data: SummarizationInput
    ) -> AgentResult[SummarizationOutput]:
        """Generate a summary with self-correction feedback loop.

        Args:
            input_data: Content and parameters for summarization

        Returns:
            AgentResult with summary or error
        """
        self.correlation_id = input_data.correlation_id
        self.log_info(
            f"Starting summarization - {len(input_data.content)} chars, lang={input_data.language}"
        )

        corrections_applied = []
        last_error = None

        for attempt in range(1, input_data.max_retries + 1):
            self.log_info(f"Summarization attempt {attempt}/{input_data.max_retries}")

            try:
                # Generate summary
                summary_result = await self._generate_summary(
                    content=input_data.content,
                    metadata=input_data.metadata,
                    language=input_data.language,
                    previous_errors=corrections_applied,
                    attempt=attempt,
                )

                if not summary_result:
                    last_error = "LLM returned no result"
                    continue

                # Validate the summary
                validation_result = await self.validator_agent.execute(
                    {"summary_json": summary_result}
                )

                if validation_result.success:
                    # Success! Return the valid summary
                    self.log_info(f"Summarization successful after {attempt} attempt(s)")

                    return AgentResult.success_result(
                        SummarizationOutput(
                            summary_json=validation_result.output["summary_json"],
                            llm_call_id=summary_result.get("llm_call_id"),
                            attempts=attempt,
                            corrections_applied=corrections_applied,
                        ),
                        attempts=attempt,
                        had_corrections=len(corrections_applied) > 0,
                    )
                else:
                    # Validation failed - record the error for feedback
                    error_msg = validation_result.error or "Unknown validation error"
                    self.log_warning(f"Validation failed (attempt {attempt}): {error_msg}")
                    corrections_applied.append(f"Attempt {attempt}: {error_msg}")
                    last_error = error_msg

            except Exception as e:
                self.log_error(f"Summarization attempt {attempt} failed: {e}")
                last_error = str(e)
                corrections_applied.append(f"Attempt {attempt}: Exception - {str(e)}")

        # All attempts exhausted
        self.log_error(
            f"Summarization failed after {input_data.max_retries} attempts. "
            f"Last error: {last_error}"
        )

        return AgentResult.error_result(
            f"Summarization failed after {input_data.max_retries} attempts: {last_error}",
            attempts=input_data.max_retries,
            corrections_attempted=corrections_applied,
        )

    async def _generate_summary(
        self,
        content: str,
        metadata: dict[str, Any],
        language: str,
        previous_errors: list[str],
        attempt: int,
    ) -> dict[str, Any] | None:
        """Generate a summary with optional feedback from previous attempts.

        This method demonstrates the feedback loop pattern for LLM summarization.
        The actual LLMSummarizer.summarize_content method requires a message object
        for sending notifications, which isn't available in the agent context.

        Integration approaches:
        1. **Validation-Only Mode**: Use this agent with pre-generated summaries
           from database to validate and refine them
        2. **Refactored Summarizer**: Extract core summarization logic to a
           message-independent method that agents can call
        3. **Hybrid Approach**: Use existing LLMSummarizer for generation,
           then use ValidationAgent for feedback loop

        Args:
            content: Content to summarize
            metadata: Metadata about the content
            language: Target language
            previous_errors: List of validation errors from previous attempts
            attempt: Current attempt number

        Returns:
            Summary result dictionary or None

        Note:
            This is a demonstration of the feedback loop pattern. For production use:
            1. Extract LLMSummarizer's core logic to a standalone method
            2. Remove message/notification dependencies
            3. Call that method here with enhanced prompts based on previous_errors
        """
        # Build enhanced feedback for retry attempts
        feedback_instructions = self._build_correction_prompt(previous_errors) if previous_errors else ""

        # In a real implementation, this would:
        # 1. Load system prompt for the language
        # 2. Add feedback_instructions to the prompt if attempt > 1
        # 3. Call a message-independent summarization method
        # 4. Return the raw JSON response

        # For now, return None to indicate this needs full integration
        # Users should use the existing LLMSummarizer directly or implement
        # the message-independent extraction first
        return None

    def _build_correction_prompt(self, errors: list[str]) -> str:
        """Build a prompt that incorporates previous validation errors.

        Args:
            errors: List of validation error messages

        Returns:
            Formatted prompt with corrections
        """
        if not errors:
            return ""

        prompt = "\n\n🔄 CORRECTIONS NEEDED FROM PREVIOUS ATTEMPT:\n"

        # Group errors by type
        char_limit_errors = [e for e in errors if "chars" in e.lower() or "character" in e.lower()]
        tag_errors = [e for e in errors if "tag" in e.lower() or "#" in e]
        field_errors = [e for e in errors if "missing" in e.lower() or "required" in e.lower()]
        json_errors = [e for e in errors if "json" in e.lower()]

        if char_limit_errors:
            prompt += "\n📏 Character Limits:\n"
            for error in char_limit_errors:
                prompt += f"  • {error}\n"

        if tag_errors:
            prompt += "\n🏷️ Topic Tags:\n"
            for error in tag_errors:
                prompt += f"  • {error}\n"

        if field_errors:
            prompt += "\n📋 Required Fields:\n"
            for error in field_errors:
                prompt += f"  • {error}\n"

        if json_errors:
            prompt += "\n🔧 JSON Structure:\n"
            for error in json_errors:
                prompt += f"  • {error}\n"

        prompt += "\nPlease generate a new summary that addresses ALL of these issues.\n"

        return prompt
