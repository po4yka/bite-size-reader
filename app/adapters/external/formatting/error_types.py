"""Error notification type constants for send_error_notification."""

from __future__ import annotations

from enum import StrEnum


class ErrorNotificationType(StrEnum):
    """Discriminator for send_error_notification error categories."""

    FIRECRAWL_ERROR = "firecrawl_error"
    EMPTY_CONTENT = "empty_content"
    PROCESSING_FAILED = "processing_failed"
    LLM_ERROR = "llm_error"
    UNEXPECTED_ERROR = "unexpected_error"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    NETWORK_ERROR = "network_error"
    DATABASE_ERROR = "database_error"
    ACCESS_DENIED = "access_denied"
    ACCESS_BLOCKED = "access_blocked"
    MESSAGE_TOO_LONG = "message_too_long"
    NO_URLS_FOUND = "no_urls_found"
    TWITTER_EXTRACTION_ERROR = "twitter_extraction_error"
