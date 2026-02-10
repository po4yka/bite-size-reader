"""Pytest configuration and shared fixtures.

This module provides common fixtures for all tests.
"""

import os
import sys
from datetime import datetime
from enum import Enum
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# Python 3.10 compatibility shims (must be before app imports)
class StrEnum(str, Enum):
    """Compatibility shim for StrEnum (Python 3.11+)."""


class _NotRequiredMeta(type):
    def __getitem__(cls, item: Any) -> Any:
        return item


class NotRequired(metaclass=_NotRequiredMeta):
    """Compatibility shim for NotRequired (Python 3.11+)."""


import datetime as dt_module
import enum
import typing
from datetime import timezone

enum.StrEnum = StrEnum  # type: ignore[misc,assignment]
typing.NotRequired = NotRequired  # type: ignore[assignment]
dt_module.UTC = timezone.utc

from app.config import (
    AdaptiveTimeoutConfig,
    AnthropicConfig,
    ApiLimitsConfig,
    AppConfig,
    AttachmentConfig,
    AuthConfig,
    BackgroundProcessorConfig,
    ChromaConfig,
    CircuitBreakerConfig,
    ContentLimitsConfig,
    DatabaseConfig,
    FirecrawlConfig,
    KarakeepConfig,
    OpenAIConfig,
    OpenRouterConfig,
    RedisConfig,
    RuntimeConfig,
    SyncConfig,
    TelegramConfig,
    TelegramLimitsConfig,
    WebSearchConfig,
    YouTubeConfig,
)
from app.config.integrations import BatchAnalysisConfig

# Provide sane defaults for integration/API tests that expect these env vars.
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-32-characters-long-123456")
# Bot token must be "digits:at-least-30-chars"
os.environ.setdefault("BOT_TOKEN", "123456789:test-token-secret-part-at-least-30-chars")
os.environ.setdefault("ALLOWED_USER_IDS", "123456789,987654321")
os.environ.setdefault("API_ID", "12345")
os.environ.setdefault("API_HASH", "test_api_hash")
os.environ.setdefault("FIRECRAWL_API_KEY", "test_firecrawl_key")
os.environ.setdefault("OPENROUTER_API_KEY", "test_openrouter_key")


@pytest.fixture(autouse=True)
def manage_database_proxy():
    """Save and restore database proxy after each test."""
    from app.db.models import database_proxy

    old_obj = database_proxy.obj
    yield
    if database_proxy.obj is not old_obj:
        database_proxy.initialize(old_obj)


@pytest.fixture(autouse=True)
def mock_chroma_client():
    """Mock ChromaDB client to prevent connection attempts."""
    # Avoid importing the real chromadb package (pydantic v1 dependency) during tests.
    chroma_stub = MagicMock()
    chroma_stub.HttpClient = MagicMock()
    chroma_stub.errors.ChromaError = Exception
    sys.modules["chromadb"] = chroma_stub
    sys.modules["chromadb.errors"] = chroma_stub.errors

    with patch("app.infrastructure.vector.chroma_store.chromadb.HttpClient") as mock_client:
        mock_instance = MagicMock()
        mock_client.return_value = mock_instance
        yield mock_instance


class MockSummaryRepository:
    """Mock summary repository for testing."""

    def __init__(self):
        """Initialize mock repository."""
        self.summaries: dict[int, dict[str, Any]] = {}
        self.next_id = 1

    async def async_upsert_summary(
        self,
        request_id: int,
        lang: str,
        json_payload: dict[str, Any],
        insights_json: dict[str, Any] | None = None,
        is_read: bool = False,
    ) -> int:
        """Mock upsert summary."""
        self.summaries[request_id] = {
            "id": self.next_id,
            "request_id": request_id,
            "lang": lang,
            "json_payload": json_payload,
            "insights_json": insights_json,
            "is_read": is_read,
            "version": 1,
            "created_at": datetime.utcnow(),
        }
        summary_id = self.next_id
        self.next_id += 1
        return summary_id

    async def async_get_summary_by_request(self, request_id: int) -> dict[str, Any] | None:
        """Mock get summary by request."""
        return self.summaries.get(request_id)

    async def async_get_unread_summaries(
        self,
        uid: int | None,
        cid: int | None,
        limit: int = 10,
        topic: str | None = None,
    ) -> list[dict[str, Any]]:
        """Mock get unread summaries."""
        unread = [
            summary for summary in self.summaries.values() if not summary.get("is_read", False)
        ]
        if topic:
            topic_lower = topic.casefold()
            unread = [
                summary
                for summary in unread
                if topic_lower in str(summary["json_payload"]).casefold()
            ]
        return unread[:limit]

    async def async_mark_summary_as_read(self, summary_id: int) -> None:
        """Mock mark summary as read."""
        for summary in self.summaries.values():
            if summary.get("id") == summary_id:
                summary["is_read"] = True
                break

    def to_domain_model(self, db_summary: dict[str, Any]) -> Any:
        """Mock conversion to domain model."""
        from app.domain.models.summary import Summary

        return Summary(
            id=db_summary.get("id"),
            request_id=db_summary["request_id"],
            content=db_summary["json_payload"],
            language=db_summary["lang"],
            version=db_summary.get("version", 1),
            is_read=db_summary.get("is_read", False),
            insights=db_summary.get("insights_json"),
            created_at=db_summary.get("created_at", datetime.utcnow()),
        )


@pytest.fixture
def mock_summary_repository():
    """Provide a mock summary repository."""
    return MockSummaryRepository()


def make_test_app_config(
    db_path: str = "/tmp/test.db",
    allowed_user_ids: tuple[int, ...] = (123456789,),
    **overrides: Any,
) -> AppConfig:
    """Create a complete AppConfig for testing with all required fields.

    Args:
        db_path: Path to the test database file.
        allowed_user_ids: Tuple of allowed Telegram user IDs.
        **overrides: Override any nested config (e.g., telegram=TelegramConfig(...)).

    Returns:
        Complete AppConfig instance suitable for testing.
    """
    defaults: dict[str, Any] = {
        "telegram": TelegramConfig(
            api_id=12345,
            api_hash="test_api_hash_placeholder_value___",
            bot_token="123456789:test-token-secret-part-at-least-30-chars",
            allowed_user_ids=allowed_user_ids,
        ),
        "firecrawl": FirecrawlConfig(api_key="fc-test-api-key-placeholder"),
        "openrouter": OpenRouterConfig(
            api_key="sk-or-test-api-key-placeholder",
            model="test/model",
            fallback_models=(),
            http_referer=None,
            x_title=None,
            max_tokens=None,
            top_p=None,
            temperature=0.2,
        ),
        "youtube": YouTubeConfig(),
        "attachment": AttachmentConfig(),
        "runtime": RuntimeConfig(
            db_path=db_path,
            log_level="INFO",
            request_timeout_sec=5,
            preferred_lang="en",
            debug_payloads=False,
        ),
        "telegram_limits": TelegramLimitsConfig(),
        "database": DatabaseConfig(),
        "content_limits": ContentLimitsConfig(),
        "vector_store": ChromaConfig(),
        "redis": RedisConfig(enabled=False),
        "api_limits": ApiLimitsConfig(),
        "auth": AuthConfig(),
        "sync": SyncConfig(),
        "background": BackgroundProcessorConfig(),
        "karakeep": KarakeepConfig(),
        "openai": OpenAIConfig(),
        "anthropic": AnthropicConfig(),
        "circuit_breaker": CircuitBreakerConfig(),
        "web_search": WebSearchConfig(),
        "adaptive_timeout": AdaptiveTimeoutConfig(),
        "batch_analysis": BatchAnalysisConfig(),
    }
    defaults.update(overrides)
    return AppConfig(**defaults)
