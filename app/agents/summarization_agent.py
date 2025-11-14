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

        Args:
            content: Content to summarize
            metadata: Metadata about the content
            language: Target language
            previous_errors: List of validation errors from previous attempts
            attempt: Current attempt number

        Returns:
            Summary result or None
        """
        # Build enhanced system prompt with feedback
        system_prompt_additions = []

        if previous_errors and attempt > 1:
            system_prompt_additions.append(
                "\n\n⚠️ IMPORTANT CORRECTIONS FROM PREVIOUS ATTEMPTS:"
            )
            for error in previous_errors[-2:]:  # Show last 2 errors
                system_prompt_additions.append(f"- {error}")
            system_prompt_additions.append(
                "\nPlease address these issues in your response."
            )

        # Add emphasis based on attempt number
        if attempt >= 2:
            system_prompt_additions.append(
                "\n\n⚠️ This is a retry. Pay special attention to:"
                "\n- Character limits on summary_250 (≤250) and summary_1000 (≤1000)"
                "\n- Topic tags must start with #"
                "\n- All required fields must be present"
                "\n- Ensure valid JSON structure"
            )

        feedback_prompt = "".join(system_prompt_additions) if system_prompt_additions else None

        # TODO: Integrate with actual LLMSummarizer.summarize() method
        # The actual implementation would call:
        # return await self.llm_summarizer.summarize(
        #     content=content,
        #     metadata=metadata,
        #     language=language,
        #     additional_instructions=feedback_prompt,
        # )

        # Placeholder implementation
        raise NotImplementedError(
            "Integration with LLMSummarizer.summarize() pending - "
            "this agent provides the feedback loop pattern"
        )

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
