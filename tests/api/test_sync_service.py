"""Tests for sync service datetime serialization safety."""

import sys
from datetime import datetime
from unittest.mock import MagicMock

# Mock redis before importing sync_service
sys.modules["redis"] = MagicMock()
sys.modules["redis.asyncio"] = MagicMock()

from app.core.time_utils import UTC


class TestSyncServiceCoerceIso:
    """Test _coerce_iso helper handles various datetime inputs."""

    def _get_sync_service(self):
        """Create a SyncService instance for testing."""
        from app.api.services.sync_service import SyncService

        mock_cfg = MagicMock()
        mock_cfg.sync.expiry_hours = 1
        mock_cfg.sync.default_limit = 200
        mock_cfg.sync.min_limit = 1
        mock_cfg.sync.max_limit = 500
        mock_cfg.redis.prefix = "test"
        return SyncService(mock_cfg)

    def test_coerce_iso_with_datetime(self):
        """Test _coerce_iso with proper datetime object."""
        service = self._get_sync_service()
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        result = service._coerce_iso(dt)
        assert result == "2024-01-15T10:30:00+00:00Z"

    def test_coerce_iso_with_naive_datetime(self):
        """Test _coerce_iso with naive datetime (no timezone)."""
        service = self._get_sync_service()
        dt = datetime(2024, 1, 15, 10, 30, 0)
        result = service._coerce_iso(dt)
        assert "2024-01-15T10:30:00" in result

    def test_coerce_iso_with_iso_string(self):
        """Test _coerce_iso with ISO string input."""
        service = self._get_sync_service()
        iso_str = "2024-01-15T10:30:00Z"
        result = service._coerce_iso(iso_str)
        assert "2024-01-15T10:30:00" in result

    def test_coerce_iso_with_none(self):
        """Test _coerce_iso with None returns current time."""
        service = self._get_sync_service()
        result = service._coerce_iso(None)
        # Should return current time in ISO format
        assert result is not None
        assert "T" in result  # ISO format has T separator
        assert result.endswith("Z")

    def test_coerce_iso_with_invalid_string(self):
        """Test _coerce_iso with invalid string returns current time."""
        service = self._get_sync_service()
        result = service._coerce_iso("not-a-date")
        # Should fallback to current time
        assert result is not None
        assert "T" in result


class TestSyncServiceSerialization:
    """Test entity serialization handles edge cases."""

    def _get_sync_service(self):
        """Create a SyncService instance for testing."""
        from app.api.services.sync_service import SyncService

        mock_cfg = MagicMock()
        mock_cfg.sync.expiry_hours = 1
        mock_cfg.sync.default_limit = 200
        mock_cfg.sync.min_limit = 1
        mock_cfg.sync.max_limit = 500
        mock_cfg.redis.prefix = "test"
        return SyncService(mock_cfg)

    def test_serialize_request_with_none_dates(self):
        """Test _serialize_request handles None datetime fields."""
        service = self._get_sync_service()

        mock_request = MagicMock()
        mock_request.id = 1
        mock_request.type = "url"
        mock_request.status = "completed"
        mock_request.input_url = "http://test.com"
        mock_request.normalized_url = "http://test.com"
        mock_request.correlation_id = "test-123"
        mock_request.server_version = 1000
        mock_request.is_deleted = False
        mock_request.created_at = None  # None datetime
        mock_request.updated_at = None  # None datetime
        mock_request.deleted_at = None

        envelope = service._serialize_request(mock_request)

        assert envelope.entity_type == "request"
        assert envelope.id == 1
        # Should not raise - _coerce_iso handles None
        assert envelope.updated_at is not None

    def test_serialize_summary_with_none_dates(self):
        """Test _serialize_summary handles None datetime fields."""
        service = self._get_sync_service()

        mock_request = MagicMock()
        mock_request.id = 1

        mock_summary = MagicMock()
        mock_summary.id = 1
        mock_summary.request = mock_request
        mock_summary.lang = "en"
        mock_summary.is_read = False
        mock_summary.json_payload = {"title": "Test"}
        mock_summary.server_version = 1000
        mock_summary.is_deleted = False
        mock_summary.created_at = None  # None datetime
        mock_summary.updated_at = None  # None datetime
        mock_summary.deleted_at = None

        envelope = service._serialize_summary(mock_summary)

        assert envelope.entity_type == "summary"
        assert envelope.id == 1
        # Should not raise - _coerce_iso handles None
        assert envelope.updated_at is not None

    def test_serialize_crawl_result_with_none_dates(self):
        """Test _serialize_crawl_result handles None datetime fields."""
        service = self._get_sync_service()

        mock_request = MagicMock()
        mock_request.id = 1

        mock_crawl = MagicMock()
        mock_crawl.id = 1
        mock_crawl.request = mock_request
        mock_crawl.source_url = "http://test.com"
        mock_crawl.endpoint = "firecrawl"
        mock_crawl.http_status = 200
        mock_crawl.metadata_json = {}
        mock_crawl.latency_ms = 100
        mock_crawl.server_version = 1000
        mock_crawl.is_deleted = False
        mock_crawl.created_at = None
        mock_crawl.updated_at = None  # None datetime
        mock_crawl.deleted_at = None

        envelope = service._serialize_crawl_result(mock_crawl)

        assert envelope.entity_type == "crawl_result"
        assert envelope.id == 1
        # Should not raise - _coerce_iso handles None
        assert envelope.updated_at is not None

    def test_serialize_llm_call_with_none_dates(self):
        """Test _serialize_llm_call handles None datetime fields."""
        service = self._get_sync_service()

        mock_request = MagicMock()
        mock_request.id = 1

        mock_call = MagicMock()
        mock_call.id = 1
        mock_call.request = mock_request
        mock_call.provider = "openrouter"
        mock_call.model = "gpt-4"
        mock_call.status = "completed"
        mock_call.tokens_prompt = 100
        mock_call.tokens_completion = 50
        mock_call.cost_usd = 0.01
        mock_call.server_version = 1000
        mock_call.is_deleted = False
        mock_call.created_at = None  # None datetime
        mock_call.updated_at = None  # None datetime
        mock_call.deleted_at = None

        envelope = service._serialize_llm_call(mock_call)

        assert envelope.entity_type == "llm_call"
        assert envelope.id == 1
        # Should not raise - _coerce_iso handles None
        assert envelope.updated_at is not None
