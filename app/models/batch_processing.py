"""Result models for batch URL processing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FailedURLDetail:
    """Detailed information about a failed URL in batch processing.

    This provides rich error context for user feedback and debugging.

    Attributes:
        url: The URL that failed
        error_type: Type of error (e.g., "timeout", "network", "validation", "circuit_breaker")
        error_message: Human-readable error message
        retry_recommended: Whether user should retry this URL
        attempts: Number of attempts made before failure
    """

    url: str
    error_type: str
    error_message: str
    retry_recommended: bool = False
    attempts: int = 1


@dataclass
class URLProcessingResult:
    """Result of processing a single URL with detailed error context.

    This replaces the simple bool return value to provide rich error information
    that can be used for retry logic, user feedback, and debugging.

    Attributes:
        url: The URL that was processed
        success: Whether processing succeeded
        error_type: Type of error if failed (e.g., "timeout", "network", "validation")
        error_message: Human-readable error message
        retry_possible: Whether this error is transient and retry makes sense
        processing_time_ms: Time taken to process in milliseconds
    """

    url: str
    success: bool
    error_type: str | None = None
    error_message: str | None = None
    retry_possible: bool = False
    processing_time_ms: float = 0.0

    @classmethod
    def success_result(cls, url: str, processing_time_ms: float = 0.0) -> URLProcessingResult:
        """Create a successful result."""
        return cls(url=url, success=True, processing_time_ms=processing_time_ms)

    @classmethod
    def error_result(
        cls,
        url: str,
        error_type: str,
        error_message: str,
        retry_possible: bool = False,
        processing_time_ms: float = 0.0,
    ) -> URLProcessingResult:
        """Create an error result."""
        return cls(
            url=url,
            success=False,
            error_type=error_type,
            error_message=error_message,
            retry_possible=retry_possible,
            processing_time_ms=processing_time_ms,
        )

    @classmethod
    def timeout_result(cls, url: str, timeout_sec: float) -> URLProcessingResult:
        """Create a timeout error result."""
        return cls.error_result(
            url=url,
            error_type="timeout",
            error_message=f"Processing timed out after {timeout_sec} seconds",
            retry_possible=True,
        )

    @classmethod
    def network_error_result(cls, url: str, error: Exception) -> URLProcessingResult:
        """Create a network error result."""
        return cls.error_result(
            url=url,
            error_type="network",
            error_message=str(error),
            retry_possible=True,
        )

    @classmethod
    def validation_error_result(cls, url: str, error: Exception) -> URLProcessingResult:
        """Create a validation error result (not retryable)."""
        return cls.error_result(
            url=url,
            error_type="validation",
            error_message=str(error),
            retry_possible=False,
        )

    @classmethod
    def generic_error_result(cls, url: str, error: Exception) -> URLProcessingResult:
        """Create a generic error result."""
        error_type = type(error).__name__
        return cls.error_result(
            url=url,
            error_type=error_type.lower(),
            error_message=str(error),
            retry_possible=False,  # Conservative: don't retry unknown errors
        )
