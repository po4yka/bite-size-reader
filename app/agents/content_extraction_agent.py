"""Content extraction agent for Firecrawl integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from app.agents.base_agent import AgentResult, BaseAgent
from app.core.url_utils import normalize_url, url_hash_sha256

if TYPE_CHECKING:
    from app.adapters.content.content_extractor import ContentExtractor
    from app.db.database import Database


class ExtractionInput(BaseModel):
    """Input for content extraction."""

    model_config = ConfigDict(frozen=True)

    url: str
    correlation_id: str
    force_refresh: bool = False


class ExtractionOutput(BaseModel):
    """Output from content extraction."""

    content_markdown: str
    content_html: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
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
        db: Database,
        correlation_id: str | None = None,
    ):
        """Initialize the content extraction agent.

        Args:
            content_extractor: The content extractor component to use
            db: Database instance for querying crawl results
            correlation_id: Optional correlation ID for tracing
        """
        super().__init__(name="ContentExtractionAgent", correlation_id=correlation_id)
        self.content_extractor = content_extractor
        self.db = db

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
            normalized_url = normalize_url(input_data.url)
            self.log_info(f"Normalized URL: {normalized_url}")

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

            validation_error = self._validate_content(result)
            if validation_error:
                self.log_warning(f"Content validation warning: {validation_error}")

            output = ExtractionOutput(
                content_markdown=result.get("content_markdown", ""),
                content_html=result.get("content_html"),
                metadata=result.get("metadata", {}),
                normalized_url=normalized_url,
                crawl_result_id=result.get("id"),
            )

            self.log_info(f"Content extraction successful - {len(output.content_markdown)} chars")

            return AgentResult.success_result(
                output,
                content_length=len(output.content_markdown),
                has_html=output.content_html is not None,
            )

        except Exception as e:
            self.log_error(f"Content extraction failed: {e}")
            return AgentResult.error_result(
                f"Content extraction error: {e!s}",
                url=input_data.url,
                exception_type=type(e).__name__,
            )

    async def _extract_with_validation(
        self, url: str, correlation_id: str
    ) -> dict[str, Any] | None:
        """Extract content with basic validation.

        This method first checks the database for existing crawl results.
        If not found, performs a fresh extraction using the message-independent
        extract_content_pure() method.

        For agent-based workflows:
        1. Check if content already exists for this URL (via dedupe hash)
        2. Return existing crawl result if available
        3. Otherwise, perform fresh extraction using extract_content_pure()

        Args:
            url: URL to extract from
            correlation_id: Correlation ID for tracing

        Returns:
            Extraction result dictionary or None if extraction fails
        """
        # Compute dedupe hash to check for existing crawl
        dedupe_hash = url_hash_sha256(url)

        existing_req = await self.db.async_get_request_by_dedupe_hash(dedupe_hash)
        if not existing_req:
            # Fallback to sync method if async not available
            existing_req = self.db.get_request_by_dedupe_hash(dedupe_hash)

        if existing_req:
            req_id = existing_req["id"]

            crawl_result = await self.db.async_get_crawl_result_by_request(req_id)
            if not crawl_result:
                # Fallback to sync method
                crawl_result = self.db.get_crawl_result_by_request(req_id)

            if crawl_result:
                self.log_info(f"Found existing crawl result (ID: {crawl_result.get('id')})")
                return {
                    "content_markdown": crawl_result.get("content_markdown", ""),
                    "content_html": crawl_result.get("content_html"),
                    "metadata": crawl_result.get("metadata_json", {}),
                    "id": crawl_result.get("id"),
                }

        # No existing crawl - perform fresh extraction
        self.log_info("No existing crawl found, performing fresh extraction")

        try:
            # Call the message-independent extraction method
            (
                content_text,
                content_source,
                metadata,
            ) = await self.content_extractor.extract_content_pure(
                url=url,
                correlation_id=correlation_id,
            )

            self.log_info(
                f"Fresh extraction successful - {len(content_text)} chars, source={content_source}"
            )

            # Return in expected format
            # Note: No crawl_result_id since we didn't persist to DB
            # (persistence is handled by the full message flow)
            return {
                "content_markdown": content_text,
                "content_html": None,  # extract_content_pure doesn't return HTML
                "metadata": metadata,
                "id": None,  # No DB record created in agent-only mode
            }

        except ValueError as e:
            # extract_content_pure raises ValueError for extraction failures
            self.log_error(f"Fresh extraction failed: {e}")
            return None
        except Exception as e:
            # Catch any other unexpected errors
            self.log_error(f"Unexpected error during extraction: {e}")
            return None

    def _validate_content(self, result: dict[str, Any]) -> str | None:
        """Validate extracted content quality.

        Args:
            result: Extraction result to validate

        Returns:
            Error message if validation fails, None otherwise
        """
        content = result.get("content_markdown", "")

        if len(content) < 100:
            return "Content too short (< 100 chars) - may be extraction failure"

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
