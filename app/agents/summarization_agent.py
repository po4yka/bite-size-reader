"""Summarization agent with self-correction feedback loop."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.agents.base_agent import AgentResult, BaseAgent

if TYPE_CHECKING:
    from app.adapters.content.llm_summarizer import LLMSummarizer

logger = logging.getLogger(__name__)
_PROMPT_DIR = Path(__file__).parent.parent / "prompts"


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

    async def execute(self, input_data: SummarizationInput) -> AgentResult[SummarizationOutput]:
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

        corrections_applied: list[str] = []
        last_error = None
        response_hashes: list[str] = []  # Track response hashes to detect ignored feedback

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

                # Calculate response hash to detect if LLM ignores feedback
                response_hash = self._calculate_response_hash(summary_result)

                # Check if this is a duplicate response (LLM ignored feedback)
                if response_hash in response_hashes:
                    self.log_warning(
                        f"Attempt {attempt}: LLM returned identical response to previous attempt. "
                        f"Feedback may be ignored. Hash: {response_hash[:16]}"
                    )
                    corrections_applied.append(
                        f"Attempt {attempt}: Duplicate response detected - LLM ignored feedback"
                    )
                    # Continue to validation anyway in case it was valid the first time

                response_hashes.append(response_hash)

                # If we have 3+ identical responses, abort early
                if response_hashes.count(response_hash) >= 3:
                    error_msg = (
                        f"LLM repeatedly returned identical response ({response_hashes.count(response_hash)} times). "
                        "Aborting as feedback is being ignored."
                    )
                    self.log_error(error_msg)
                    return AgentResult.error_result(
                        error_msg,
                        attempts=attempt,
                        corrections_attempted=corrections_applied,
                        feedback_ignored=True,
                    )

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
                # Validation failed - record the error for feedback
                error_msg = validation_result.error or "Unknown validation error"
                self.log_warning(f"Validation failed (attempt {attempt}): {error_msg}")
                corrections_applied.append(f"Attempt {attempt}: {error_msg}")
                last_error = error_msg

            except Exception as e:
                self.log_error(f"Summarization attempt {attempt} failed: {e}")
                last_error = str(e)
                corrections_applied.append(f"Attempt {attempt}: Exception - {e!s}")

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

        This method implements the feedback loop pattern for LLM summarization,
        using the message-independent summarize_content_pure() method.

        Args:
            content: Content to summarize
            metadata: Metadata about the content
            language: Target language
            previous_errors: List of validation errors from previous attempts
            attempt: Current attempt number

        Returns:
            Summary result dictionary or None if generation fails
        """
        # Load system prompt for the language
        system_prompt = self._get_system_prompt(language)

        # Build enhanced feedback for retry attempts
        feedback_instructions = None
        if previous_errors:
            feedback_instructions = self._build_correction_prompt(previous_errors)
            self.log_info(f"Retry attempt {attempt} with {len(previous_errors)} previous error(s)")

        try:
            # Call the message-independent summarization method
            return await self.llm_summarizer.summarize_content_pure(
                content_text=content,
                chosen_lang=language,
                system_prompt=system_prompt,
                correlation_id=self.correlation_id,
                feedback_instructions=feedback_instructions,
            )

        except ValueError as e:
            # summarize_content_pure raises ValueError for summarization failures
            self.log_error(f"Summarization failed on attempt {attempt}: {e}")
            return None
        except Exception as e:
            # Catch any other unexpected errors
            self.log_error(f"Unexpected error during summarization attempt {attempt}: {e}")
            return None

    def _get_system_prompt(self, lang: str) -> str:
        """Load and cache the system prompt for the given language.

        Args:
            lang: Language code ('en' or 'ru')

        Returns:
            System prompt text
        """
        fname = "summary_system_ru.txt" if lang == "ru" else "summary_system_en.txt"
        path = _PROMPT_DIR / fname
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception as e:
            self.log_warning(f"Failed to load system prompt from {path}: {e}")
            return "You are a precise assistant that returns only a strict JSON object matching the provided schema."

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

    def _calculate_response_hash(self, response: dict[str, Any]) -> str:
        """Calculate a hash of the response to detect duplicates.

        Args:
            response: The LLM response dictionary

        Returns:
            SHA256 hash of the normalized response
        """
        try:
            # Normalize response by sorting keys for consistent hashing
            normalized = json.dumps(response, sort_keys=True, ensure_ascii=False)
            return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        except Exception as e:
            self.log_warning(f"Failed to calculate response hash: {e}")
            # Return a random hash on error to avoid false positives
            return hashlib.sha256(str(id(response)).encode()).hexdigest()
