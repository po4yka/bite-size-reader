"""Unit tests for Karakeep sync integration.

Covers:
- _ensure_datetime: None, datetime, valid ISO string, timezone-aware string,
  invalid string, non-string type
- SyncResult.items_skipped: computed field summing all skip-reason fields
- _SyncWorkItem: dataclass creation with defaults and all fields
- _apply_bookmark_metadata: tag attachment, favourite update, counter tracking
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

from app.adapters.karakeep.models import KarakeepBookmark, SyncResult
from app.adapters.karakeep.sync_service import (
    KarakeepSyncService,
    _ensure_datetime,
    _SyncWorkItem,
)

# ---------------------------------------------------------------------------
# _ensure_datetime tests
# ---------------------------------------------------------------------------


class TestEnsureDatetime(unittest.TestCase):
    """Test the _ensure_datetime helper for robust datetime coercion."""

    def test_none_returns_none(self):
        """None input should return None without error."""
        assert _ensure_datetime(None) is None

    def test_naive_datetime_gets_utc(self):
        """A naive datetime should get UTC tzinfo attached."""
        dt = datetime(2025, 6, 15, 12, 30, 0)
        result = _ensure_datetime(dt)
        assert result is not None
        assert result.tzinfo is UTC
        assert result == datetime(2025, 6, 15, 12, 30, 0, tzinfo=UTC)

    def test_aware_datetime_returns_same(self):
        """An aware datetime should be returned unchanged."""
        dt = datetime(2025, 6, 15, 12, 30, 0, tzinfo=UTC)
        result = _ensure_datetime(dt)
        assert result is dt

    def test_iso_string_returns_parsed_datetime(self):
        """A naive ISO format string should be parsed into a UTC-aware datetime."""
        iso = "2025-06-15T12:30:00"
        result = _ensure_datetime(iso)
        assert isinstance(result, datetime)
        assert result.tzinfo is UTC
        assert result.year == 2025
        assert result.month == 6
        assert result.day == 15
        assert result.hour == 12
        assert result.minute == 30

    def test_iso_string_with_timezone(self):
        """An ISO string with timezone offset should be parsed correctly."""
        iso_tz = "2025-06-15T12:30:00+03:00"
        result = _ensure_datetime(iso_tz)
        assert isinstance(result, datetime)
        assert result.tzinfo is not None
        assert result.year == 2025
        assert result.hour == 12

    def test_iso_string_utc_z_suffix(self):
        """An ISO string with Z suffix (UTC) should be parsed correctly."""
        iso_z = "2025-06-15T12:30:00+00:00"
        result = _ensure_datetime(iso_z)
        assert isinstance(result, datetime)
        assert result.tzinfo is not None

    def test_invalid_string_returns_none(self):
        """A non-parseable string should return None."""
        result = _ensure_datetime("not-a-date")
        assert result is None

    def test_empty_string_returns_none(self):
        """An empty string should return None."""
        result = _ensure_datetime("")
        assert result is None

    def test_integer_returns_none(self):
        """An integer (non-datetime/non-string) should return None."""
        result = _ensure_datetime(12345)
        assert result is None

    def test_float_returns_none(self):
        """A float should return None."""
        result = _ensure_datetime(1718451000.0)
        assert result is None

    def test_list_returns_none(self):
        """A list should return None."""
        result = _ensure_datetime([2025, 6, 15])
        assert result is None

    def test_dict_returns_none(self):
        """A dict should return None."""
        result = _ensure_datetime({"year": 2025})
        assert result is None


# ---------------------------------------------------------------------------
# SyncResult.items_skipped computed field tests
# ---------------------------------------------------------------------------


class TestSyncResultItemsSkipped(unittest.TestCase):
    """Test the computed items_skipped property on SyncResult."""

    def test_default_all_zeros(self):
        """Default SyncResult should have items_skipped == 0."""
        result = SyncResult(direction="bsr_to_karakeep")
        assert result.items_skipped == 0

    def test_single_skip_field(self):
        """Setting one skip field should be reflected in items_skipped."""
        result = SyncResult(direction="bsr_to_karakeep", skipped_already_synced=5)
        assert result.items_skipped == 5

    def test_another_single_skip_field(self):
        """Setting skipped_exists_in_target alone should be reflected."""
        result = SyncResult(direction="karakeep_to_bsr", skipped_exists_in_target=3)
        assert result.items_skipped == 3

    def test_skipped_hash_failed_alone(self):
        """Setting skipped_hash_failed alone should be reflected."""
        result = SyncResult(direction="bsr_to_karakeep", skipped_hash_failed=2)
        assert result.items_skipped == 2

    def test_skipped_no_url_alone(self):
        """Setting skipped_no_url alone should be reflected."""
        result = SyncResult(direction="bsr_to_karakeep", skipped_no_url=7)
        assert result.items_skipped == 7

    def test_multiple_skip_fields_sum(self):
        """Multiple skip fields should sum correctly."""
        result = SyncResult(
            direction="bsr_to_karakeep",
            skipped_already_synced=10,
            skipped_exists_in_target=5,
            skipped_hash_failed=2,
            skipped_no_url=3,
        )
        assert result.items_skipped == 20

    def test_items_skipped_in_model_dump(self):
        """items_skipped should appear in model_dump() output."""
        result = SyncResult(
            direction="bsr_to_karakeep",
            skipped_already_synced=4,
            skipped_exists_in_target=1,
        )
        dumped = result.model_dump()
        assert "items_skipped" in dumped
        assert dumped["items_skipped"] == 5

    def test_items_synced_independent_of_skipped(self):
        """items_synced should not affect items_skipped."""
        result = SyncResult(
            direction="bsr_to_karakeep",
            items_synced=100,
            skipped_already_synced=3,
        )
        assert result.items_skipped == 3
        assert result.items_synced == 100

    def test_items_failed_independent_of_skipped(self):
        """items_failed should not affect items_skipped."""
        result = SyncResult(
            direction="bsr_to_karakeep",
            items_failed=7,
            skipped_no_url=2,
        )
        assert result.items_skipped == 2
        assert result.items_failed == 7

    def test_all_counters_independent(self):
        """synced, failed, and skipped should all be independent."""
        result = SyncResult(
            direction="karakeep_to_bsr",
            items_synced=50,
            items_failed=3,
            skipped_already_synced=10,
            skipped_exists_in_target=5,
            skipped_hash_failed=1,
            skipped_no_url=2,
        )
        assert result.items_synced == 50
        assert result.items_failed == 3
        assert result.items_skipped == 18


# ---------------------------------------------------------------------------
# _SyncWorkItem dataclass tests
# ---------------------------------------------------------------------------


class TestSyncWorkItem(unittest.TestCase):
    """Test the _SyncWorkItem dataclass."""

    def test_create_with_required_fields_only(self):
        """Creating with only required fields should default existing_bookmark to None."""
        summary = {"id": 1, "request_data": {"normalized_url": "https://example.com"}}
        item = _SyncWorkItem(summary_data=summary, url_hash="abc123")
        assert item.summary_data is summary
        assert item.url_hash == "abc123"
        assert item.existing_bookmark is None

    def test_create_with_all_fields(self):
        """Creating with all fields, including existing_bookmark."""
        summary = {"id": 2, "request_data": {"normalized_url": "https://example.org"}}
        bookmark = KarakeepBookmark(id="bk-1", url="https://example.org")
        item = _SyncWorkItem(summary_data=summary, url_hash="def456", existing_bookmark=bookmark)
        assert item.summary_data is summary
        assert item.url_hash == "def456"
        assert item.existing_bookmark is bookmark
        assert item.existing_bookmark.id == "bk-1"

    def test_access_summary_data_fields(self):
        """Should be able to navigate into summary_data dict."""
        summary = {
            "id": 10,
            "request_data": {"normalized_url": "https://example.com/article"},
            "json_payload": {"tldr": "A test summary"},
        }
        item = _SyncWorkItem(summary_data=summary, url_hash="hash1")
        assert item.summary_data["id"] == 10
        assert item.summary_data["request_data"]["normalized_url"] == "https://example.com/article"
        assert item.summary_data["json_payload"]["tldr"] == "A test summary"

    def test_url_hash_stored_correctly(self):
        """url_hash should store the exact value provided."""
        long_hash = "a" * 64
        item = _SyncWorkItem(summary_data={"id": 1}, url_hash=long_hash)
        assert item.url_hash == long_hash
        assert len(item.url_hash) == 64


# ---------------------------------------------------------------------------
# _apply_bookmark_metadata integration test (mocked client)
# ---------------------------------------------------------------------------


class TestApplyBookmarkMetadata(unittest.IsolatedAsyncioTestCase):
    """Test _apply_bookmark_metadata with a mocked Karakeep client."""

    def _make_service(self) -> KarakeepSyncService:
        """Create a KarakeepSyncService with no real dependencies."""
        return KarakeepSyncService(
            api_url="http://localhost:3000/api/v1",
            api_key="test-api-key",
            sync_tag="bsr-synced",
            repository=None,
            client_factory=None,
        )

    def _make_bookmark(
        self,
        bookmark_id: str = "bk-100",
        url: str = "https://example.com/article",
        favourited: bool = False,
    ) -> KarakeepBookmark:
        """Create a minimal KarakeepBookmark for testing."""
        return KarakeepBookmark(
            id=bookmark_id,
            url=url,
            favourited=favourited,
            modified_at=datetime(2025, 6, 1, tzinfo=UTC),  # type: ignore[call-arg]
        )

    def _make_summary_data(
        self,
        *,
        summary_id: int = 42,
        is_favorited: bool = False,
        is_read: bool = False,
        topic_tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Build a summary_data dict matching the shape expected by sync service."""
        json_payload: dict[str, Any] = {}
        if topic_tags is not None:
            json_payload["topic_tags"] = topic_tags
        return {
            "id": summary_id,
            "is_favorited": is_favorited,
            "is_read": is_read,
            "json_payload": json_payload,
        }

    async def test_tags_attached_no_favourite(self):
        """Tags should be attached; favourite should not be updated when not favorited."""
        service = self._make_service()
        client = AsyncMock()
        # attach_tags returns None (the real client returns None)
        client.attach_tags = AsyncMock(return_value=None)
        client.update_bookmark = AsyncMock()

        bookmark = self._make_bookmark()
        summary_data = self._make_summary_data(
            topic_tags=["#python", "#testing"],
        )
        counters: dict[str, int] = {"tags_attached": 0, "favourites_updated": 0}

        errors, _last_modified = await service._apply_bookmark_metadata(
            client,
            bookmark=bookmark,
            summary_data=summary_data,
            correlation_id="test-corr-001",
            counters=counters,
        )

        assert errors == []
        # attach_tags should have been called with bsr-synced + topic tags
        client.attach_tags.assert_called_once()
        call_args = client.attach_tags.call_args
        attached_bookmark_id = call_args[0][0]
        attached_tags = call_args[0][1]
        assert attached_bookmark_id == "bk-100"
        assert "bsr-synced" in attached_tags
        assert "python" in attached_tags
        assert "testing" in attached_tags
        # update_bookmark should NOT have been called (not favorited)
        client.update_bookmark.assert_not_called()
        # Counters should reflect 3 tags (bsr-synced + python + testing)
        assert counters["tags_attached"] == 3
        assert counters["favourites_updated"] == 0

    async def test_favourite_updated(self):
        """When is_favorited is True, update_bookmark should be called with favourited=True."""
        service = self._make_service()
        updated_bookmark = self._make_bookmark(favourited=True)
        updated_bookmark.modified_at = datetime(2025, 7, 1, tzinfo=UTC)

        client = AsyncMock()
        client.update_bookmark = AsyncMock(return_value=updated_bookmark)
        client.attach_tags = AsyncMock(return_value=None)

        bookmark = self._make_bookmark()
        summary_data = self._make_summary_data(is_favorited=True)
        counters: dict[str, int] = {"tags_attached": 0, "favourites_updated": 0}

        errors, last_modified = await service._apply_bookmark_metadata(
            client,
            bookmark=bookmark,
            summary_data=summary_data,
            correlation_id="test-corr-002",
            counters=counters,
        )

        assert errors == []
        # update_bookmark should have been called with favourited=True
        client.update_bookmark.assert_called_once_with("bk-100", favourited=True)
        assert counters["favourites_updated"] == 1
        # last_modified should reflect the updated bookmark
        assert last_modified == datetime(2025, 7, 1, tzinfo=UTC)

    async def test_read_summary_includes_bsr_read_tag(self):
        """When is_read is True, bsr-read tag should be included in attach_tags."""
        service = self._make_service()
        client = AsyncMock()
        client.attach_tags = AsyncMock(return_value=None)
        client.update_bookmark = AsyncMock()

        bookmark = self._make_bookmark()
        summary_data = self._make_summary_data(is_read=True)
        counters: dict[str, int] = {"tags_attached": 0, "favourites_updated": 0}

        errors, _last_modified = await service._apply_bookmark_metadata(
            client,
            bookmark=bookmark,
            summary_data=summary_data,
            correlation_id="test-corr-003",
            counters=counters,
        )

        assert errors == []
        client.attach_tags.assert_called_once()
        attached_tags = client.attach_tags.call_args[0][1]
        assert "bsr-synced" in attached_tags
        assert "bsr-read" in attached_tags

    async def test_return_tuple_structure(self):
        """Return value should be (list_of_errors, datetime_or_none)."""
        service = self._make_service()
        client = AsyncMock()
        client.attach_tags = AsyncMock(return_value=None)

        bookmark = self._make_bookmark()
        summary_data = self._make_summary_data()

        result = await service._apply_bookmark_metadata(
            client,
            bookmark=bookmark,
            summary_data=summary_data,
            correlation_id="test-corr-004",
        )

        assert isinstance(result, tuple)
        assert len(result) == 2
        errors, last_modified = result
        assert isinstance(errors, list)
        # last_modified should be datetime or None
        assert last_modified is None or isinstance(last_modified, datetime)

    async def test_tag_attachment_failure_recorded_as_non_fatal(self):
        """If attach_tags fails, error should be recorded but not raised."""
        service = self._make_service()
        client = AsyncMock()
        client.attach_tags = AsyncMock(side_effect=Exception("tag API down"))
        client.update_bookmark = AsyncMock()

        bookmark = self._make_bookmark()
        summary_data = self._make_summary_data()
        counters: dict[str, int] = {"tags_attached": 0, "favourites_updated": 0}

        errors, _last_modified = await service._apply_bookmark_metadata(
            client,
            bookmark=bookmark,
            summary_data=summary_data,
            correlation_id="test-corr-005",
            counters=counters,
        )

        # Should have recorded the error as non-fatal
        assert len(errors) == 1
        error_msg, _retryable = errors[0]
        assert "Failed to attach tags" in error_msg
        # Tags counter should not have been incremented
        assert counters["tags_attached"] == 0

    async def test_favourite_failure_recorded_as_non_fatal(self):
        """If update_bookmark for favourite fails, error should be non-fatal."""
        service = self._make_service()
        client = AsyncMock()
        client.update_bookmark = AsyncMock(side_effect=Exception("bookmark API down"))
        client.attach_tags = AsyncMock(return_value=None)

        bookmark = self._make_bookmark()
        summary_data = self._make_summary_data(is_favorited=True)
        counters: dict[str, int] = {"tags_attached": 0, "favourites_updated": 0}

        errors, _last_modified = await service._apply_bookmark_metadata(
            client,
            bookmark=bookmark,
            summary_data=summary_data,
            correlation_id="test-corr-006",
            counters=counters,
        )

        # Should have favourite error recorded
        fav_errors = [e for e, _ in errors if "favourite" in e.lower()]
        assert len(fav_errors) == 1
        assert counters["favourites_updated"] == 0

    async def test_topic_tags_stripped_of_hash(self):
        """Topic tags should have leading # stripped before being sent to Karakeep."""
        service = self._make_service()
        client = AsyncMock()
        client.attach_tags = AsyncMock(return_value=None)

        bookmark = self._make_bookmark()
        summary_data = self._make_summary_data(topic_tags=["#AI", "#machine-learning", "#NLP"])

        await service._apply_bookmark_metadata(
            client,
            bookmark=bookmark,
            summary_data=summary_data,
            correlation_id="test-corr-007",
        )

        client.attach_tags.assert_called_once()
        attached_tags = client.attach_tags.call_args[0][1]
        # Tags should not have leading #
        for tag in attached_tags:
            assert not tag.startswith("#"), f"Tag '{tag}' should not start with #"
        assert "AI" in attached_tags
        assert "machine-learning" in attached_tags
        assert "NLP" in attached_tags

    async def test_no_counters_provided(self):
        """Should work fine when counters=None is passed."""
        service = self._make_service()
        client = AsyncMock()
        client.attach_tags = AsyncMock(return_value=None)

        bookmark = self._make_bookmark()
        summary_data = self._make_summary_data(is_read=True, topic_tags=["#test"])

        # Should not raise
        errors, _last_modified = await service._apply_bookmark_metadata(
            client,
            bookmark=bookmark,
            summary_data=summary_data,
            correlation_id="test-corr-008",
            counters=None,
        )

        assert errors == []


if __name__ == "__main__":
    unittest.main()
