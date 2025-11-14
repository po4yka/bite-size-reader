"""Validation agent for enforcing summary JSON contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.base_agent import AgentResult, BaseAgent
from app.core.summary_contract import validate_summary_json


@dataclass
class ValidationInput:
    """Input for validation."""

    summary_json: dict[str, Any]


@dataclass
class ValidationOutput:
    """Output from validation."""

    summary_json: dict[str, Any]
    validation_warnings: list[str]
    corrections_applied: list[str]


class ValidationAgent(BaseAgent[ValidationInput, ValidationOutput]):
    """Agent responsible for enforcing summary JSON contract.

    This agent:
    - Validates all required fields are present
    - Enforces character limits (250, 1000)
    - Checks topic tag formatting (#prefix)
    - Deduplicates entities (case-insensitive)
    - Validates data types and structure
    - Provides detailed error messages for corrections
    """

    def __init__(self, correlation_id: str | None = None):
        """Initialize the validation agent.

        Args:
            correlation_id: Optional correlation ID for tracing
        """
        super().__init__(name="ValidationAgent", correlation_id=correlation_id)

    async def execute(self, input_data: ValidationInput) -> AgentResult[ValidationOutput]:
        """Validate summary JSON against strict contract.

        Args:
            input_data: Summary JSON to validate

        Returns:
            AgentResult with validated summary or detailed errors
        """
        summary = input_data.summary_json
        self.log_info("Starting summary validation")

        errors = []
        warnings = []
        corrections = []

        try:
            # Required fields check
            required_fields = [
                "summary_250",
                "summary_1000",
                "tldr",
                "key_ideas",
                "topic_tags",
                "entities",
                "estimated_reading_time_min",
                "key_stats",
                "answered_questions",
                "readability",
                "seo_keywords",
            ]

            missing_fields = [f for f in required_fields if f not in summary]
            if missing_fields:
                errors.append(f"Missing required fields: {', '.join(missing_fields)}")

            # Character limit validation
            if "summary_250" in summary:
                length_250 = len(summary["summary_250"])
                if length_250 > 250:
                    errors.append(
                        f"summary_250 exceeds limit: {length_250} chars (max 250). "
                        f"Truncate to last sentence boundary before 250 chars."
                    )
                elif length_250 < 50:
                    warnings.append(f"summary_250 very short: {length_250} chars")

            if "summary_1000" in summary:
                length_1000 = len(summary["summary_1000"])
                if length_1000 > 1000:
                    errors.append(
                        f"summary_1000 exceeds limit: {length_1000} chars (max 1000). "
                        f"Truncate to last sentence boundary before 1000 chars."
                    )
                elif length_1000 < 100:
                    warnings.append(f"summary_1000 very short: {length_1000} chars")

            # Topic tags validation
            if "topic_tags" in summary:
                tags = summary["topic_tags"]
                if not isinstance(tags, list):
                    errors.append("topic_tags must be a list")
                else:
                    invalid_tags = [t for t in tags if not str(t).startswith("#")]
                    if invalid_tags:
                        errors.append(
                            f"Topic tags missing '#' prefix: {', '.join(invalid_tags)}"
                        )

                    if len(tags) > 10:
                        warnings.append(f"Many topic tags: {len(tags)} (recommend ≤10)")

            # Entities validation
            if "entities" in summary:
                entities = summary["entities"]
                if not isinstance(entities, dict):
                    errors.append("entities must be a dictionary")
                else:
                    required_entity_types = ["people", "organizations", "locations"]
                    for entity_type in required_entity_types:
                        if entity_type not in entities:
                            errors.append(f"entities.{entity_type} is required")
                        elif not isinstance(entities[entity_type], list):
                            errors.append(f"entities.{entity_type} must be a list")

            # Key stats validation
            if "key_stats" in summary:
                stats = summary["key_stats"]
                if not isinstance(stats, list):
                    errors.append("key_stats must be a list")
                else:
                    for idx, stat in enumerate(stats):
                        if not isinstance(stat, dict):
                            errors.append(f"key_stats[{idx}] must be a dictionary")
                            continue

                        if "label" not in stat:
                            errors.append(f"key_stats[{idx}] missing 'label' field")
                        if "value" not in stat:
                            errors.append(f"key_stats[{idx}] missing 'value' field")
                        elif not isinstance(stat["value"], (int, float)):
                            errors.append(
                                f"key_stats[{idx}].value must be numeric, "
                                f"got {type(stat['value']).__name__}"
                            )

            # Readability validation
            if "readability" in summary:
                readability = summary["readability"]
                if not isinstance(readability, dict):
                    errors.append("readability must be a dictionary")
                else:
                    if "score" not in readability:
                        errors.append("readability.score is required")
                    elif not isinstance(readability["score"], (int, float)):
                        errors.append("readability.score must be numeric")

                    if "level" not in readability:
                        warnings.append("readability.level missing (recommended)")

            # Estimated reading time validation
            if "estimated_reading_time_min" in summary:
                reading_time = summary["estimated_reading_time_min"]
                if not isinstance(reading_time, int):
                    errors.append(
                        f"estimated_reading_time_min must be integer, "
                        f"got {type(reading_time).__name__}"
                    )
                elif reading_time < 1:
                    warnings.append(f"estimated_reading_time_min very low: {reading_time}")

            # If there are errors, return error result with details
            if errors:
                error_message = self._format_validation_errors(errors)
                self.log_error(f"Validation failed: {len(errors)} error(s)")
                return AgentResult.error_result(
                    error_message, error_count=len(errors), warnings=warnings
                )

            # Use the existing validation function for final check
            try:
                validated_summary = validate_summary_json(summary)
                self.log_info("Summary validation successful")

                if warnings:
                    self.log_warning(f"Validation warnings: {'; '.join(warnings)}")

                return AgentResult.success_result(
                    ValidationOutput(
                        summary_json=validated_summary,
                        validation_warnings=warnings,
                        corrections_applied=corrections,
                    ),
                    warning_count=len(warnings),
                )

            except Exception as e:
                self.log_error(f"Contract validation failed: {e}")
                return AgentResult.error_result(
                    f"Summary contract validation failed: {str(e)}", exception_type=type(e).__name__
                )

        except Exception as e:
            self.log_error(f"Validation error: {e}")
            return AgentResult.error_result(
                f"Validation exception: {str(e)}", exception_type=type(e).__name__
            )

    def _format_validation_errors(self, errors: list[str]) -> str:
        """Format validation errors into a clear message.

        Args:
            errors: List of error messages

        Returns:
            Formatted error string
        """
        if len(errors) == 1:
            return errors[0]

        formatted = f"Found {len(errors)} validation errors:\n"
        for idx, error in enumerate(errors, 1):
            formatted += f"{idx}. {error}\n"

        return formatted.strip()
