"""Integration test: full URL→scraper→LLM→DB pipeline.

Constructs a real URLProcessor with stub scraper and stub LLM, runs
handle_url_flow(), and asserts a summary row is persisted in the DB.
No external I/O — all network boundaries are stubbed with canned responses.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import make_test_app_config
from tests.integration.helpers import temp_db

_CANNED_MARKDOWN = """
# Test Article

This is a comprehensive test article about software engineering.

## Key Points

- Testing is essential for quality software
- Integration tests verify the full pipeline
- Stub components enable isolated testing

The article concludes that robust testing leads to reliable systems.
"""

_MINIMAL_SUMMARY_JSON = json.dumps(
    {
        "tldr": "Testing ensures software quality.",
        "summary_250": "A test article about software engineering and testing practices.",
        "summary_1000": (
            "This comprehensive article covers software engineering fundamentals. "
            "Key points include the importance of testing, integration tests for full "
            "pipeline verification, and using stubs for isolation."
        ),
        "key_ideas": [
            "Testing is essential",
            "Integration tests verify pipelines",
            "Stubs enable isolation",
        ],
        "topic_tags": ["#testing", "#software-engineering"],
        "entities": [{"name": "software engineering", "type": "topic"}],
        "estimated_reading_time_min": 2,
        "source_type": "article",
        "readability": {"score": 8, "level": "accessible", "method": "Flesch-Kincaid"},
        "key_stats": [],
        "answered_questions": [],
        "seo_keywords": ["testing", "software engineering", "integration tests"],
    }
)


def _make_stub_scraper():
    from app.adapters.external.firecrawl.models import FirecrawlResult

    scraper = MagicMock()
    scraper.provider_name = "stub"
    scraper.scrape_markdown = AsyncMock(
        return_value=FirecrawlResult(
            status="ok",
            http_status=200,
            content_markdown=_CANNED_MARKDOWN,
        )
    )
    scraper.aclose = AsyncMock()
    return scraper


def _make_stub_llm():
    from app.models.llm.llm_models import LLMCallResult

    llm = MagicMock()
    llm.provider_name = "stub"
    llm.chat = AsyncMock(
        return_value=LLMCallResult(
            status="ok",
            response_text=_MINIMAL_SUMMARY_JSON,
            response_json=None,
            openrouter_response_text=None,
            openrouter_response_json=None,
        )
    )
    llm.aclose = AsyncMock()
    return llm


def _make_stub_response_formatter():
    # AsyncMock auto-creates async methods for any attribute access
    fmt = AsyncMock()
    # These need specific non-async return values
    fmt.is_draft_streaming_enabled = MagicMock(return_value=False)
    fmt.send_structured_summary_response = AsyncMock(return_value=None)
    fmt._lang = "en"
    return fmt


class FakeMessage:
    def __init__(self, uid: int = 1):
        class _User:
            def __init__(self, id):
                self.id = id

        class _Chat:
            id = 1

        self.chat = _Chat()
        self.from_user = _User(uid)
        self._replies: list[str] = []
        self.id = 999
        self.message_id = 999

    async def reply_text(self, text: str, **kwargs) -> None:
        self._replies.append(text)


@pytest.mark.integration
class TestUrlPipelineIntegration(unittest.IsolatedAsyncioTestCase):
    """Validates the full URL→scraper→LLM→DB orchestration seam."""

    async def asyncSetUp(self) -> None:
        from app.db.models import database_proxy

        self._old_proxy_obj = database_proxy.obj

    async def asyncTearDown(self) -> None:
        from app.db.models import database_proxy

        if database_proxy.obj is not self._old_proxy_obj:
            database_proxy.initialize(self._old_proxy_obj)

    async def test_handle_url_flow_persists_summary_to_db(self) -> None:
        """Full pipeline: stub scraper + stub LLM → summary row in SQLite."""
        from app.adapters.content.url_flow_models import URLFlowRequest
        from app.adapters.content.url_processor import URLProcessor
        from app.db.models import Summary

        with temp_db() as db:
            cfg = make_test_app_config(
                db_path=db.database.database,
                allowed_user_ids=(1,),
            )
            scraper = _make_stub_scraper()
            llm = _make_stub_llm()
            fmt = _make_stub_response_formatter()

            sem_lock = asyncio.Semaphore(1)

            def sem():
                return sem_lock

            with patch("app.adapters.content.content_extractor.RedisCache") as mock_redis_cls:
                mock_redis = MagicMock()
                mock_redis.enabled = False
                mock_redis.clear = AsyncMock(return_value=0)
                mock_redis.get_json = AsyncMock(return_value=None)
                mock_redis.set_json = AsyncMock()
                mock_redis_cls.return_value = mock_redis

                processor = URLProcessor(
                    cfg=cfg,
                    db=db,
                    firecrawl=scraper,
                    openrouter=llm,
                    response_formatter=fmt,
                    audit_func=lambda *a, **kw: None,
                    sem=sem,
                )

            url = "https://example.com/test-article"
            message = FakeMessage(uid=1)

            request = URLFlowRequest(
                message=message,
                url_text=url,
                correlation_id="test-cid-001",
                interaction_id=None,
                silent=True,
            )

            await processor.handle_url_flow(request)

            await processor.aclose()

            # Verify a summary row was written to the DB
            summaries = list(Summary.select())
            assert summaries, "Expected at least one summary row in DB after handle_url_flow"
            payload = summaries[0].json_payload
            # json_payload may be returned as a dict (Peewee JSON field) or a JSON string
            summary_data = json.loads(payload) if isinstance(payload, str) else payload
            assert "tldr" in summary_data
            assert "summary_250" in summary_data


if __name__ == "__main__":
    unittest.main()
