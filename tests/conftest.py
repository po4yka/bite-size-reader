"""Pytest configuration and shared fixtures.

This module provides common fixtures for all tests.
"""

import os
from datetime import datetime
from typing import Any

import pytest

# Provide sane defaults for integration/API tests that expect these env vars.
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-32-characters-long-123456")
os.environ.setdefault("BOT_TOKEN", "test_token")
os.environ.setdefault("ALLOWED_USER_IDS", "123456789")


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
        self, uid: int, cid: int, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Mock get unread summaries."""
        unread = [
            summary for summary in self.summaries.values() if not summary.get("is_read", False)
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
