"""Use case for summarizing a URL.

This is the core use case of the application, orchestrating the complete
workflow from URL to final summary.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.domain.events.request_events import RequestCompleted, RequestCreated, RequestFailed
from app.domain.events.summary_events import SummaryCreated
from app.domain.exceptions.domain_exceptions import (
    ContentFetchError,
    SummaryGenerationError,
)
from app.domain.models.request import Request, RequestStatus, RequestType
from app.domain.models.summary import Summary
from app.domain.services.summary_validator import SummaryValidator
from app.infrastructure.persistence.sqlite.repositories.crawl_result_repository import (
    SqliteCrawlResultRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.request_repository import (
    SqliteRequestRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)

logger = logging.getLogger(__name__)


@dataclass
class SummarizeUrlCommand:
    """Command for summarizing a URL.

    This is an explicit representation of the user's intent to summarize content.
    """

    url: str
    user_id: int
    chat_id: int
    language: str | None = None
    correlation_id: str | None = None
    input_message_id: int | None = None

    def __post_init__(self) -> None:
        """Validate command parameters."""
        if not self.url or not self.url.strip():
            raise ValueError("url must not be empty")
        if self.user_id <= 0:
            raise ValueError("user_id must be positive")
        if self.chat_id <= 0:
            raise ValueError("chat_id must be positive")


@dataclass
class SummarizeUrlResult:
    """Result of URL summarization workflow.

    Contains the created request, summary, and any events generated.
    """

    request: Request
    summary: Summary
    events: list[Any]  # List of domain events


class SummarizeUrlUseCase:
    """Use case for complete URL summarization workflow.

    This use case orchestrates the entire process:
    1. Create request record
    2. Fetch content (via external service)
    3. Generate summary (via LLM)
    4. Validate summary
    5. Persist summary
    6. Generate domain events
    7. Update request status

    This demonstrates a complex workflow in the hexagonal architecture.

    Example:
        ```python
        use_case = SummarizeUrlUseCase(
            request_repo=request_repo,
            summary_repo=summary_repo,
            crawl_result_repo=crawl_result_repo,
            content_fetcher=content_fetcher,  # External service
            llm_client=llm_client,            # External service
            summary_validator=SummaryValidator(),
        )

        command = SummarizeUrlCommand(
            url="https://example.com/article",
            user_id=123,
            chat_id=456,
            language="en",
            correlation_id="abc-123",
        )

        result = await use_case.execute(command)
        # result.request - created request
        # result.summary - generated summary
        # result.events - [RequestCreated, SummaryCreated, RequestCompleted]
        ```
    """

    def __init__(
        self,
        request_repository: SqliteRequestRepositoryAdapter,
        summary_repository: SqliteSummaryRepositoryAdapter,
        crawl_result_repository: SqliteCrawlResultRepositoryAdapter,
        content_fetcher: Any,  # IContentFetcher protocol (external service)
        llm_client: Any,  # ILLMClient protocol (external service)
        summary_validator: SummaryValidator,
    ) -> None:
        """Initialize the use case.

        Args:
            request_repository: Repository for request persistence.
            summary_repository: Repository for summary persistence.
            crawl_result_repository: Repository for crawl result persistence.
            content_fetcher: Service for fetching content from URLs.
            llm_client: Service for generating summaries via LLM.
            summary_validator: Domain service for validating summaries.
        """
        self._request_repo = request_repository
        self._summary_repo = summary_repository
        self._crawl_result_repo = crawl_result_repository
        self._content_fetcher = content_fetcher
        self._llm_client = llm_client
        self._validator = summary_validator

    async def execute(self, command: SummarizeUrlCommand) -> SummarizeUrlResult:
        """Execute the complete URL summarization workflow.

        Args:
            command: Command containing URL and user details.

        Returns:
            Result containing request, summary, and events.

        Raises:
            ContentFetchError: If content cannot be fetched.
            SummaryGenerationError: If summary cannot be generated.
            ValidationError: If summary fails validation.
        """
        events: list[Any] = []

        logger.info(
            "summarize_url_started",
            extra={
                "url": command.url,
                "user_id": command.user_id,
                "cid": command.correlation_id,
            },
        )

        # 1. Create request record
        request = await self._create_request(command)
        events.append(
            RequestCreated(
                occurred_at=datetime.utcnow(),
                aggregate_id=request.id,
                request_id=request.id or 0,
                user_id=request.user_id,
                chat_id=request.chat_id,
                request_type=request.request_type.value,
            )
        )

        try:
            # 2. Fetch content
            request, content = await self._fetch_content(request, command)

            # 3. Generate summary
            request, summary = await self._generate_summary(request, command, content)

            # 4. Validate summary
            self._validator.validate_summary(summary)

            # 5. Persist summary
            await self._persist_summary(summary)

            # 6. Mark request as completed
            request.mark_as_completed()
            await self._request_repo.async_update_request_status(
                request.id or 0, request.status.value
            )

            # 7. Generate events
            events.append(
                SummaryCreated(
                    occurred_at=datetime.utcnow(),
                    aggregate_id=summary.id,
                    summary_id=summary.id or 0,
                    request_id=summary.request_id,
                    language=summary.language,
                    has_insights=summary.has_insights(),
                )
            )

            events.append(
                RequestCompleted(
                    occurred_at=datetime.utcnow(),
                    aggregate_id=request.id,
                    request_id=request.id or 0,
                    summary_id=summary.id,
                )
            )

            logger.info(
                "summarize_url_completed",
                extra={
                    "request_id": request.id,
                    "summary_id": summary.id,
                    "cid": command.correlation_id,
                },
            )

            return SummarizeUrlResult(
                request=request,
                summary=summary,
                events=events,
            )

        except Exception as e:
            # Mark request as failed
            request.mark_as_error()
            await self._request_repo.async_update_request_status(
                request.id or 0, request.status.value
            )

            # Generate failure event
            events.append(
                RequestFailed(
                    occurred_at=datetime.utcnow(),
                    aggregate_id=request.id,
                    request_id=request.id or 0,
                    error_message=str(e),
                    error_details={"url": command.url, "user_id": command.user_id},
                )
            )

            logger.exception(
                "summarize_url_failed",
                extra={
                    "request_id": request.id,
                    "error": str(e),
                    "cid": command.correlation_id,
                },
            )

            raise

    async def _create_request(self, command: SummarizeUrlCommand) -> Request:
        """Create and persist initial request record.

        Args:
            command: Command containing request details.

        Returns:
            Created Request domain model with ID.
        """
        logger.debug("creating_request", extra={"url": command.url})

        # Create domain model
        request = Request(
            user_id=command.user_id,
            chat_id=command.chat_id,
            request_type=RequestType.URL,
            status=RequestStatus.PENDING,
            input_url=command.url,
            correlation_id=command.correlation_id,
            input_message_id=command.input_message_id,
        )

        # Persist
        # Note: In full implementation, we'd use from_domain_model
        # For now, direct call to repository
        request_id = await self._request_repo.async_create_request(
            uid=request.user_id,
            cid=request.chat_id,
            url=request.input_url,
            correlation_id=request.correlation_id,
        )

        request.id = request_id
        return request

    async def _fetch_content(
        self, request: Request, command: SummarizeUrlCommand
    ) -> tuple[Request, dict[str, Any]]:
        """Fetch content from URL.

        Args:
            request: Request domain model.
            command: Original command.

        Returns:
            Tuple of (updated request, content dict).

        Raises:
            ContentFetchError: If content cannot be fetched.
        """
        logger.debug("fetching_content", extra={"url": command.url})

        # Update request status
        request.mark_as_crawling()
        await self._request_repo.async_update_request_status(
            request.id or 0, request.status.value
        )

        try:
            # Call external service (this would be the actual implementation)
            # For now, this is a placeholder showing the pattern
            # content = await self._content_fetcher.fetch(command.url)

            # In real implementation, this would return structured content
            # For now, return placeholder
            content = {
                "text": "Content placeholder",
                "markdown": "# Markdown placeholder",
                "metadata": {},
            }

            # Persist crawl result
            await self._crawl_result_repo.async_insert_crawl_result(
                request_id=request.id or 0,
                success=True,
                markdown=content.get("markdown"),
                metadata_json=content.get("metadata"),
            )

            return request, content

        except Exception as e:
            # Persist failed crawl result
            await self._crawl_result_repo.async_insert_crawl_result(
                request_id=request.id or 0,
                success=False,
                error=str(e),
            )

            raise ContentFetchError(
                f"Failed to fetch content from {command.url}: {e}",
                details={"url": command.url, "error": str(e)},
            ) from e

    async def _generate_summary(
        self, request: Request, command: SummarizeUrlCommand, content: dict[str, Any]
    ) -> tuple[Request, Summary]:
        """Generate summary from content.

        Args:
            request: Request domain model.
            command: Original command.
            content: Fetched content.

        Returns:
            Tuple of (updated request, generated summary).

        Raises:
            SummaryGenerationError: If summary cannot be generated.
        """
        logger.debug("generating_summary", extra={"request_id": request.id})

        # Update request status
        request.mark_as_summarizing()
        await self._request_repo.async_update_request_status(
            request.id or 0, request.status.value
        )

        try:
            # Call LLM service (this would be the actual implementation)
            # For now, this is a placeholder showing the pattern
            # llm_response = await self._llm_client.chat(messages=[...])

            # In real implementation, this would return structured summary
            # For now, return placeholder
            summary_content = {
                "tldr": "This is a summary placeholder",
                "summary_250": "Brief summary placeholder",
                "summary_1000": "Detailed summary placeholder",
                "key_ideas": ["Key idea 1", "Key idea 2"],
                "topic_tags": ["tag1", "tag2"],
                "entities": [],
                "seo_keywords": ["keyword1", "keyword2"],
                "estimated_reading_time_min": 5,
            }

            # Create summary domain model
            summary = Summary(
                request_id=request.id or 0,
                content=summary_content,
                language=command.language or "en",
                version=1,
                is_read=False,
            )

            return request, summary

        except Exception as e:
            raise SummaryGenerationError(
                f"Failed to generate summary: {e}",
                details={"request_id": request.id, "error": str(e)},
            ) from e

    async def _persist_summary(self, summary: Summary) -> None:
        """Persist summary to database.

        Args:
            summary: Summary domain model to persist.
        """
        logger.debug("persisting_summary", extra={"request_id": summary.request_id})

        version = await self._summary_repo.async_upsert_summary(
            request_id=summary.request_id,
            lang=summary.language,
            json_payload=summary.content,
            insights_json=summary.insights,
            is_read=summary.is_read,
        )

        # Update summary with version
        summary.version = version

        logger.debug(
            "summary_persisted",
            extra={"request_id": summary.request_id, "version": version},
        )
