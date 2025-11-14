"""Content extraction agent for Firecrawl integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.agents.base_agent import AgentResult, BaseAgent
from app.core.url_utils import normalize_url

if TYPE_CHECKING:
    from app.adapters.content.content_extractor import ContentExtractor


@dataclass
class ExtractionInput:
    """Input for content extraction."""

    url: str
    correlation_id: str
    force_refresh: bool = False


@dataclass
class ExtractionOutput:
    """Output from content extraction."""

    content_markdown: str
    content_html: str | None
    metadata: dict[str, Any]
    normalized_url: str
    crawl_result_id: int | None = None


class ContentExtractionAgent(BaseAgent[ExtractionInput, ExtractionOutput]):
    """Agent responsible for extracting content from URLs using Firecrawl.

    This agent:
    - Normalizes URLs for consistency
    - Calls Firecrawl API to extract content
    - Validates extracted content quality
    - Persists crawl results to database
    - Provides retry logic with exponential backoff
    """

    def __init__(
        self,
        content_extractor: ContentExtractor,
        correlation_id: str | None = None,
    ):
        """Initialize the content extraction agent.

        Args:
            content_extractor: The content extractor component to use
            correlation_id: Optional correlation ID for tracing
        """
        super().__init__(name="ContentExtractionAgent", correlation_id=correlation_id)
        self.content_extractor = content_extractor

    async def execute(self, input_data: ExtractionInput) -> AgentResult[ExtractionOutput]:
        """Extract content from the given URL.

        Args:
            input_data: Extraction parameters including URL

        Returns:
            AgentResult with extracted content or error
        """
        self.correlation_id = input_data.correlation_id
        self.log_info(f"Starting content extraction for URL: {input_data.url}")

        try:
            # Normalize URL
            normalized_url = normalize_url(input_data.url)
            self.log_info(f"Normalized URL: {normalized_url}")

            # Extract content using existing component
            # Note: The ContentExtractor.extract() method handles:
            # - Firecrawl API calls
            # - Database persistence
            # - Retry logic
            # - Error handling
            result = await self._extract_with_validation(
                url=normalized_url,
                correlation_id=input_data.correlation_id,
            )

            if not result:
                return AgentResult.error_result(
                    "Content extraction failed - no result returned",
                    url=input_data.url,
                )

            # Validate extracted content
            validation_error = self._validate_content(result)
            if validation_error:
                self.log_warning(f"Content validation warning: {validation_error}")

            # Build output
            output = ExtractionOutput(
                content_markdown=result.get("content_markdown", ""),
                content_html=result.get("content_html"),
                metadata=result.get("metadata", {}),
                normalized_url=normalized_url,
                crawl_result_id=result.get("id"),
            )

            self.log_info(
                f"Content extraction successful - {len(output.content_markdown)} chars"
            )

            return AgentResult.success_result(
                output,
                content_length=len(output.content_markdown),
                has_html=output.content_html is not None,
            )

        except Exception as e:
            self.log_error(f"Content extraction failed: {e}")
            return AgentResult.error_result(
                f"Content extraction error: {str(e)}",
                url=input_data.url,
                exception_type=type(e).__name__,
            )

    async def _extract_with_validation(
        self, url: str, correlation_id: str
    ) -> dict[str, Any] | None:
        """Extract content with basic validation.

        This is a wrapper around the existing ContentExtractor that would
        ideally call its extract method. Since we're building on top of
        existing code, this serves as an integration point.

        Args:
            url: URL to extract from
            correlation_id: Correlation ID for tracing

        Returns:
            Extraction result dictionary or None
        """
        # TODO: Integrate with actual ContentExtractor.extract() method
        # For now, this is a placeholder showing the intended interface
        # The actual implementation would call:
        # return await self.content_extractor.extract(url, correlation_id)

        # Placeholder implementation
        raise NotImplementedError(
            "Integration with ContentExtractor.extract() pending - "
            "this agent provides the multi-agent wrapper pattern"
        )

    def _validate_content(self, result: dict[str, Any]) -> str | None:
        """Validate extracted content quality.

        Args:
            result: Extraction result to validate

        Returns:
            Error message if validation fails, None otherwise
        """
        content = result.get("content_markdown", "")

        # Check minimum content length
        if len(content) < 100:
            return "Content too short (< 100 chars) - may be extraction failure"

        # Check for error indicators in content
        error_indicators = [
            "access denied",
            "404 not found",
            "page not found",
            "forbidden",
            "cloudflare",
        ]

        content_lower = content.lower()
        for indicator in error_indicators:
            if indicator in content_lower and len(content) < 500:
                return f"Content may contain error page ('{indicator}' detected)"

        return None
