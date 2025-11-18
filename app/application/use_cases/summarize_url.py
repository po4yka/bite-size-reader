"""Use case for summarizing a URL.

This is the core use case of the application, orchestrating the complete
workflow from URL to final summary.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.lang import LANG_EN, detect_language
from app.core.time_utils import UTC
from app.domain.events.request_events import RequestCompleted, RequestCreated, RequestFailed
from app.domain.events.summary_events import SummaryCreated
from app.domain.exceptions.domain_exceptions import ContentFetchError, SummaryGenerationError
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
from app.protocols import ContentFetcher, SummaryGenerator

logger = logging.getLogger(__name__)

# Path to prompt files
_PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"


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
            msg = "url must not be empty"
            raise ValueError(msg)
        if self.user_id <= 0:
            msg = "user_id must be positive"
            raise ValueError(msg)
        if self.chat_id <= 0:
            msg = "chat_id must be positive"
            raise ValueError(msg)


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
        # Initialize repositories
        request_repo = SqliteRequestRepositoryAdapter(database)
        summary_repo = SqliteSummaryRepositoryAdapter(database)
        crawl_result_repo = SqliteCrawlResultRepositoryAdapter(database)

        # Initialize services (ContentExtractor and LLMSummarizer implement the protocols)
        content_extractor = ContentExtractor(cfg, db, firecrawl, response_formatter, audit_func, sem)
        llm_summarizer = LLMSummarizer(cfg, db, openrouter_client, response_formatter, audit_func)

        # Create use case
        use_case = SummarizeUrlUseCase(
            request_repository=request_repo,
            summary_repository=summary_repo,
            crawl_result_repository=crawl_result_repo,
            content_fetcher=content_extractor,  # Implements ContentFetcher protocol
            llm_client=llm_summarizer,          # Implements SummaryGenerator protocol
            summary_validator=SummaryValidator(),
        )

        # Execute the use case
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
        content_fetcher: ContentFetcher,
        llm_client: SummaryGenerator,
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
                occurred_at=datetime.now(UTC),
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
                    occurred_at=datetime.now(UTC),
                    aggregate_id=summary.id,
                    summary_id=summary.id or 0,
                    request_id=summary.request_id,
                    language=summary.language,
                    has_insights=summary.has_insights(),
                )
            )

            events.append(
                RequestCompleted(
                    occurred_at=datetime.now(UTC),
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
                    occurred_at=datetime.now(UTC),
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
        await self._request_repo.async_update_request_status(request.id or 0, request.status.value)

        try:
            # Call content fetcher service to extract content
            (
                content_text,
                content_source,
                metadata,
            ) = await self._content_fetcher.extract_content_pure(
                url=command.url,
                correlation_id=command.correlation_id,
            )

            # Detect language from content if not specified
            detected_lang = detect_language(content_text)
            if detected_lang:
                await self._request_repo.async_update_request_lang_detected(
                    request.id or 0, detected_lang
                )

            # Persist crawl result
            # Store the original markdown/html in the database
            markdown_content = metadata.get("markdown") or content_text
            await self._crawl_result_repo.async_insert_crawl_result(
                request_id=request.id or 0,
                success=True,
                markdown=markdown_content if isinstance(markdown_content, str) else None,
                metadata_json=metadata if isinstance(metadata, dict) else None,
            )

            # Return structured content for next step
            content = {
                "text": content_text,
                "source": content_source,
                "metadata": metadata,
                "detected_lang": detected_lang,
            }

            logger.info(
                "content_fetched",
                extra={
                    "request_id": request.id,
                    "content_length": len(content_text),
                    "source": content_source,
                    "detected_lang": detected_lang,
                    "cid": command.correlation_id,
                },
            )

            return request, content

        except Exception as e:
            # Persist failed crawl result
            await self._crawl_result_repo.async_insert_crawl_result(
                request_id=request.id or 0,
                success=False,
                error=str(e),
            )

            msg = f"Failed to fetch content from {command.url}: {e}"
            raise ContentFetchError(
                msg,
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
        await self._request_repo.async_update_request_status(request.id or 0, request.status.value)

        try:
            # Determine language for summary
            # Priority: command.language > detected_lang > default
            detected_lang = content.get("detected_lang", LANG_EN)
            summary_lang = command.language or detected_lang or LANG_EN

            # Load system prompt for the chosen language
            system_prompt = self._load_system_prompt(summary_lang)

            # Call LLM service to generate summary
            summary_content = await self._llm_client.summarize_content_pure(
                content_text=content["text"],
                chosen_lang=summary_lang,
                system_prompt=system_prompt,
                correlation_id=command.correlation_id,
                feedback_instructions=None,
            )

            # Create summary domain model
            summary = Summary(
                request_id=request.id or 0,
                content=summary_content,
                language=summary_lang,
                version=1,
                is_read=False,
            )

            logger.info(
                "summary_generated",
                extra={
                    "request_id": request.id,
                    "language": summary_lang,
                    "has_key_ideas": bool(summary_content.get("key_ideas")),
                    "has_topic_tags": bool(summary_content.get("topic_tags")),
                    "cid": command.correlation_id,
                },
            )

            return request, summary

        except Exception as e:
            msg = f"Failed to generate summary: {e}"
            raise SummaryGenerationError(
                msg,
                details={"request_id": request.id, "error": str(e)},
            ) from e

    def _load_system_prompt(self, lang: str) -> str:
        """Load system prompt for the given language.

        Args:
            lang: Language code ('en' or 'ru').

        Returns:
            System prompt text.

        """
        fname = "summary_system_ru.txt" if lang == "ru" else "summary_system_en.txt"
        path = _PROMPT_DIR / fname
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.warning(
                "failed_to_load_system_prompt",
                extra={"path": str(path), "error": str(e)},
            )
            # Fallback to a basic prompt
            return "You are a precise assistant that returns only a strict JSON object matching the provided schema."

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
