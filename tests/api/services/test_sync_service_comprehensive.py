"""Comprehensive tests for sync service to boost coverage above 80%."""

import json
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock redis before importing sync_service
sys.modules["redis"] = MagicMock()
sys.modules["redis.asyncio"] = MagicMock()

from app.api.exceptions import (
    SyncSessionExpiredError,
    SyncSessionForbiddenError,
    SyncSessionNotFoundError,
)
from app.api.models.responses import SyncEntityEnvelope
from app.api.services.sync_service import SyncService
from app.core.time_utils import UTC


def make_sync_envelope(
    entity_type: str = "request",
    entity_id: int = 1,
    server_version: int = 1,
    deleted_at: str | None = None,
) -> SyncEntityEnvelope:
    """Helper to create SyncEntityEnvelope instances for testing."""
    return SyncEntityEnvelope(
        entity_type=entity_type,
        id=entity_id,
        server_version=server_version,
        updated_at=datetime.now(UTC).isoformat() + "Z",
        deleted_at=deleted_at,
    )


@pytest.fixture
def mock_config():
    """Create mock AppConfig."""
    cfg = MagicMock()
    cfg.sync.expiry_hours = 2
    cfg.sync.default_limit = 200
    cfg.sync.min_limit = 10
    cfg.sync.max_limit = 500
    cfg.redis.prefix = "test"
    cfg.redis.enabled = False
    return cfg


@pytest.fixture
def mock_session_manager():
    """Create mock DatabaseSessionManager."""
    return MagicMock()


@pytest.fixture
def sync_service(mock_config, mock_session_manager):
    """Create SyncService instance with mocked dependencies."""
    with (
        patch("app.api.services.sync_service.SqliteUserRepositoryAdapter"),
        patch("app.api.services.sync_service.SqliteRequestRepositoryAdapter"),
        patch("app.api.services.sync_service.SqliteSummaryRepositoryAdapter"),
        patch("app.api.services.sync_service.SqliteCrawlResultRepositoryAdapter"),
        patch("app.api.services.sync_service.SqliteLLMRepositoryAdapter"),
    ):
        service = SyncService(mock_config, mock_session_manager)
        # Mock the repositories
        service._user_repo = MagicMock()
        service._request_repo = MagicMock()
        service._summary_repo = MagicMock()
        service._crawl_repo = MagicMock()
        service._llm_repo = MagicMock()
        return service


class TestResolveLimit:
    """Test _resolve_limit method."""

    def test_resolve_limit_with_none(self, sync_service):
        """Test with None returns default limit."""
        result = sync_service._resolve_limit(None)
        assert result == 200  # default_limit

    def test_resolve_limit_below_min(self, sync_service):
        """Test with value below min returns min limit."""
        result = sync_service._resolve_limit(5)
        assert result == 10  # min_limit

    def test_resolve_limit_above_max(self, sync_service):
        """Test with value above max returns max limit."""
        result = sync_service._resolve_limit(1000)
        assert result == 500  # max_limit

    def test_resolve_limit_within_range(self, sync_service):
        """Test with valid value returns that value."""
        result = sync_service._resolve_limit(100)
        assert result == 100


class TestStoreSession:
    """Test _store_session method."""

    @pytest.mark.asyncio
    async def test_store_session_redis_available(self, sync_service, mock_config):
        """Test storing session when Redis is available."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()

        with patch("app.api.services.sync_service.get_redis", return_value=mock_redis):
            payload = {
                "session_id": "test-session",
                "user_id": 123,
                "client_id": "test-client",
            }

            await sync_service._store_session(payload)

            mock_redis.set.assert_called_once()
            call_args = mock_redis.set.call_args
            assert "test:sync:session:test-session" in call_args[0][0]
            assert json.loads(call_args[0][1]) == payload
            assert call_args[1]["ex"] == int(mock_config.sync.expiry_hours * 3600)

    @pytest.mark.asyncio
    async def test_store_session_redis_unavailable_fallback(self, sync_service):
        """Test fallback to in-memory when Redis unavailable."""
        with patch("app.api.services.sync_service.get_redis", return_value=None):
            payload = {
                "session_id": "test-session-fallback",
                "user_id": 456,
                "client_id": "test-client",
            }

            # Reset the warning flag to test logging
            import app.api.services.sync_service

            app.api.services.sync_service._redis_warning_logged = False

            await sync_service._store_session(payload)

            # Check in-memory storage
            from app.api.services.sync_service import _sync_sessions

            assert "test-session-fallback" in _sync_sessions
            assert _sync_sessions["test-session-fallback"] == payload


class TestLoadSession:
    """Test _load_session method."""

    @pytest.mark.asyncio
    async def test_load_session_redis_success(self, sync_service):
        """Test loading session from Redis successfully."""
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=1)
        payload = {
            "session_id": "test-session",
            "user_id": 123,
            "client_id": "test-client",
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        }

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(payload))
        mock_redis.ttl = AsyncMock(return_value=3600)

        with patch("app.api.services.sync_service.get_redis", return_value=mock_redis):
            result = await sync_service._load_session("test-session", 123, "test-client")

            assert result == payload
            mock_redis.get.assert_called_once()
            mock_redis.ttl.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_session_redis_not_found(self, sync_service):
        """Test loading non-existent session from Redis."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.ttl = AsyncMock(return_value=-2)

        with patch("app.api.services.sync_service.get_redis", return_value=mock_redis):
            with pytest.raises(SyncSessionNotFoundError) as exc_info:
                await sync_service._load_session("missing-session", 123, "test-client")

            assert "missing-session" in str(exc_info.value.details.get("session_id", ""))

    @pytest.mark.asyncio
    async def test_load_session_fallback_not_found(self, sync_service):
        """Test loading from in-memory fallback when session not found."""
        with patch("app.api.services.sync_service.get_redis", return_value=None):
            with pytest.raises(SyncSessionNotFoundError):
                await sync_service._load_session("missing-session", 123, "test-client")

    @pytest.mark.asyncio
    async def test_load_session_forbidden_wrong_user(self, sync_service):
        """Test loading session with mismatched user_id."""
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=1)
        payload = {
            "session_id": "test-session",
            "user_id": 123,
            "client_id": "test-client",
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        }

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(payload))
        mock_redis.ttl = AsyncMock(return_value=3600)

        with patch("app.api.services.sync_service.get_redis", return_value=mock_redis):
            with pytest.raises(SyncSessionForbiddenError):
                await sync_service._load_session("test-session", 999, "test-client")

    @pytest.mark.asyncio
    async def test_load_session_forbidden_wrong_client(self, sync_service):
        """Test loading session with mismatched client_id."""
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=1)
        payload = {
            "session_id": "test-session",
            "user_id": 123,
            "client_id": "test-client",
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        }

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(payload))
        mock_redis.ttl = AsyncMock(return_value=3600)

        with patch("app.api.services.sync_service.get_redis", return_value=mock_redis):
            with pytest.raises(SyncSessionForbiddenError):
                await sync_service._load_session("test-session", 123, "wrong-client")

    @pytest.mark.asyncio
    async def test_load_session_expired(self, sync_service):
        """Test loading expired session."""
        now = datetime.now(UTC)
        expires_at = now - timedelta(hours=1)  # Expired
        payload = {
            "session_id": "test-session",
            "user_id": 123,
            "client_id": "test-client",
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        }

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(payload))
        mock_redis.ttl = AsyncMock(return_value=100)

        with patch("app.api.services.sync_service.get_redis", return_value=mock_redis):
            with pytest.raises(SyncSessionExpiredError) as exc_info:
                await sync_service._load_session("test-session", 123, "test-client")

            assert "test-session" in str(exc_info.value.details.get("session_id", ""))


class TestStartSession:
    """Test start_session method."""

    @pytest.mark.asyncio
    async def test_start_session_success(self, sync_service, mock_config):
        """Test starting a new session successfully."""
        with patch.object(sync_service, "_store_session", new_callable=AsyncMock) as mock_store:
            result = await sync_service.start_session(
                user_id=123, client_id="test-client", limit=100
            )

            assert result.session_id.startswith("sync-")
            assert result.default_limit == 200
            assert result.max_limit == 500
            assert result.last_issued_since == 0
            mock_store.assert_called_once()

            # Verify stored payload
            stored_payload = mock_store.call_args[0][0]
            assert stored_payload["user_id"] == 123
            assert stored_payload["client_id"] == "test-client"
            assert stored_payload["chunk_limit"] == 100

    @pytest.mark.asyncio
    async def test_start_session_with_none_limit(self, sync_service):
        """Test starting session with None limit uses default."""
        with patch.object(sync_service, "_store_session", new_callable=AsyncMock) as mock_store:
            result = await sync_service.start_session(
                user_id=123, client_id="test-client", limit=None
            )

            stored_payload = mock_store.call_args[0][0]
            assert stored_payload["chunk_limit"] == 200  # default_limit


class TestCollectRecords:
    """Test _collect_records method."""

    @pytest.mark.asyncio
    async def test_collect_records_all_types(self, sync_service):
        """Test collecting all entity types."""
        # Mock user
        sync_service._user_repo.async_get_user_by_telegram_id = AsyncMock(
            return_value={"telegram_user_id": 123, "username": "test", "server_version": 1}
        )

        # Mock requests
        sync_service._request_repo.async_get_all_for_user = AsyncMock(
            return_value=[
                {
                    "id": "req-1",
                    "type": "url",
                    "status": "completed",
                    "server_version": 2,
                    "is_deleted": False,
                }
            ]
        )

        # Mock summaries
        sync_service._summary_repo.async_get_all_for_user = AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "request": 1,
                    "lang": "en",
                    "server_version": 3,
                    "is_deleted": False,
                }
            ]
        )

        # Mock crawl results
        sync_service._crawl_repo.async_get_all_for_user = AsyncMock(
            return_value=[
                {
                    "id": 10,
                    "request": 1,
                    "source_url": "http://test.com",
                    "server_version": 4,
                    "is_deleted": False,
                }
            ]
        )

        # Mock LLM calls
        sync_service._llm_repo.async_get_all_for_user = AsyncMock(
            return_value=[
                {
                    "id": 20,
                    "request": 1,
                    "provider": "openrouter",
                    "server_version": 5,
                    "is_deleted": False,
                }
            ]
        )

        records = await sync_service._collect_records(123)

        assert len(records) == 5
        assert records[0].entity_type == "user"
        assert records[1].entity_type == "request"
        assert records[2].entity_type == "summary"
        assert records[3].entity_type == "crawl_result"
        assert records[4].entity_type == "llm_call"

    @pytest.mark.asyncio
    async def test_collect_records_no_user(self, sync_service):
        """Test collecting when user not found."""
        sync_service._user_repo.async_get_user_by_telegram_id = AsyncMock(return_value=None)
        sync_service._request_repo.async_get_all_for_user = AsyncMock(return_value=[])
        sync_service._summary_repo.async_get_all_for_user = AsyncMock(return_value=[])
        sync_service._crawl_repo.async_get_all_for_user = AsyncMock(return_value=[])
        sync_service._llm_repo.async_get_all_for_user = AsyncMock(return_value=[])

        records = await sync_service._collect_records(123)

        assert len(records) == 0


class TestPaginateRecords:
    """Test _paginate_records method."""

    def test_paginate_records_first_page(self, sync_service):
        """Test paginating first page."""
        records = [
            make_sync_envelope(entity_id=i, server_version=i) for i in range(1, 11)
        ]  # 10 records, versions 1-10

        page, has_more, _next_since = sync_service._paginate_records(records, since=0, limit=5)

        assert len(page) == 5
        assert has_more is True
        assert _next_since == 5

    def test_paginate_records_last_page(self, sync_service):
        """Test paginating last page."""
        records = [
            make_sync_envelope(entity_id=i, server_version=i) for i in range(1, 4)
        ]  # 3 records

        page, has_more, _next_since = sync_service._paginate_records(records, since=0, limit=5)

        assert len(page) == 3
        assert has_more is False
        assert _next_since == 3

    def test_paginate_records_with_since(self, sync_service):
        """Test paginating with since cursor."""
        records = [make_sync_envelope(entity_id=i, server_version=i) for i in range(1, 11)]

        page, has_more, _next_since = sync_service._paginate_records(records, since=5, limit=3)

        assert len(page) == 3
        assert all(r.server_version > 5 for r in page)
        assert has_more is True

    def test_paginate_records_empty(self, sync_service):
        """Test paginating with no records."""
        records = []

        page, has_more, _next_since = sync_service._paginate_records(records, since=0, limit=5)

        assert len(page) == 0
        assert has_more is False
        assert _next_since == 0


class TestGetFull:
    """Test get_full method."""

    @pytest.mark.asyncio
    async def test_get_full_success(self, sync_service):
        """Test full sync retrieval."""
        now = datetime.now(UTC)
        session_payload = {
            "session_id": "test-session",
            "user_id": 123,
            "client_id": "test-client",
            "chunk_limit": 100,
            "expires_at": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        }

        with patch.object(
            sync_service, "_load_session", new_callable=AsyncMock, return_value=session_payload
        ):
            with patch.object(
                sync_service, "_collect_records", new_callable=AsyncMock
            ) as mock_collect:
                mock_collect.return_value = [
                    make_sync_envelope(entity_id=i, server_version=i) for i in range(1, 6)
                ]

                result = await sync_service.get_full(
                    session_id="test-session", user_id=123, client_id="test-client", limit=10
                )

                assert result.session_id == "test-session"
                assert len(result.items) == 5
                assert result.has_more is False
                assert result.pagination.total == 5

    @pytest.mark.asyncio
    async def test_get_full_with_pagination(self, sync_service):
        """Test full sync with pagination."""
        now = datetime.now(UTC)
        session_payload = {
            "session_id": "test-session",
            "user_id": 123,
            "client_id": "test-client",
            "chunk_limit": 5,
            "expires_at": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        }

        with patch.object(
            sync_service, "_load_session", new_callable=AsyncMock, return_value=session_payload
        ):
            with patch.object(
                sync_service, "_collect_records", new_callable=AsyncMock
            ) as mock_collect:
                # 200+ records to ensure pagination with limit=100
                mock_collect.return_value = [
                    make_sync_envelope(entity_id=i, server_version=i) for i in range(1, 151)
                ]

                # Use limit=50 to override session chunk_limit
                result = await sync_service.get_full(
                    session_id="test-session", user_id=123, client_id="test-client", limit=50
                )

                assert len(result.items) == 50
                assert result.has_more is True
                assert result.next_since == 50


class TestGetDelta:
    """Test get_delta method."""

    @pytest.mark.asyncio
    async def test_get_delta_success(self, sync_service):
        """Test delta sync retrieval."""
        now = datetime.now(UTC)
        session_payload = {
            "session_id": "test-session",
            "user_id": 123,
            "client_id": "test-client",
            "chunk_limit": 100,
            "expires_at": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        }

        with patch.object(
            sync_service, "_load_session", new_callable=AsyncMock, return_value=session_payload
        ):
            with patch.object(
                sync_service, "_collect_records", new_callable=AsyncMock
            ) as mock_collect:
                mock_collect.return_value = [
                    make_sync_envelope(entity_id=i, server_version=i, deleted_at=None)
                    for i in range(5, 8)
                ]

                result = await sync_service.get_delta(
                    session_id="test-session",
                    user_id=123,
                    client_id="test-client",
                    since=4,
                    limit=10,
                )

                assert result.session_id == "test-session"
                assert result.since == 4
                assert len(result.created) == 3
                assert len(result.updated) == 0
                assert len(result.deleted) == 0

    @pytest.mark.asyncio
    async def test_get_delta_with_deletions(self, sync_service):
        """Test delta sync with deleted items."""
        now = datetime.now(UTC)
        session_payload = {
            "session_id": "test-session",
            "user_id": 123,
            "client_id": "test-client",
            "chunk_limit": 100,
            "expires_at": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        }

        with patch.object(
            sync_service, "_load_session", new_callable=AsyncMock, return_value=session_payload
        ):
            with patch.object(
                sync_service, "_collect_records", new_callable=AsyncMock
            ) as mock_collect:
                deleted_time = now.isoformat() + "Z"
                mock_collect.return_value = [
                    make_sync_envelope(entity_id=5, server_version=5, deleted_at=None),
                    make_sync_envelope(entity_id=6, server_version=6, deleted_at=deleted_time),
                ]

                result = await sync_service.get_delta(
                    session_id="test-session",
                    user_id=123,
                    client_id="test-client",
                    since=4,
                    limit=10,
                )

                assert len(result.created) == 1
                assert len(result.deleted) == 1
                assert result.deleted[0].id == 6


class TestApplyChanges:
    """Test apply_changes method."""

    @pytest.mark.asyncio
    async def test_apply_changes_unsupported_entity(self, sync_service):
        """Test applying changes with unsupported entity type."""
        now = datetime.now(UTC)
        session_payload = {
            "session_id": "test-session",
            "user_id": 123,
            "client_id": "test-client",
            "expires_at": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        }

        from app.api.models.requests import SyncApplyItem

        changes = [
            SyncApplyItem(
                entity_type="request",  # Unsupported
                id=1,
                action="update",
                last_seen_version=1,
                payload={},
            )
        ]

        with patch.object(
            sync_service, "_load_session", new_callable=AsyncMock, return_value=session_payload
        ):
            result = await sync_service.apply_changes(
                session_id="test-session", user_id=123, client_id="test-client", changes=changes
            )

            assert len(result.results) == 1
            assert result.results[0].status == "invalid"
            assert result.results[0].error_code == "UNSUPPORTED_ENTITY"

    @pytest.mark.asyncio
    async def test_apply_changes_summary_success(self, sync_service):
        """Test applying summary changes successfully."""
        now = datetime.now(UTC)
        session_payload = {
            "session_id": "test-session",
            "user_id": 123,
            "client_id": "test-client",
            "expires_at": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        }

        from app.api.models.requests import SyncApplyItem

        changes = [
            SyncApplyItem(
                entity_type="summary",
                id=1,
                action="update",
                last_seen_version=5,
                payload={"is_read": True},
            )
        ]

        sync_service._summary_repo.async_get_summary_for_sync_apply = AsyncMock(
            return_value={"id": 1, "server_version": 5, "is_read": False}
        )
        sync_service._summary_repo.async_apply_sync_change = AsyncMock(return_value=6)

        with patch.object(
            sync_service, "_load_session", new_callable=AsyncMock, return_value=session_payload
        ):
            result = await sync_service.apply_changes(
                session_id="test-session", user_id=123, client_id="test-client", changes=changes
            )

            assert len(result.results) == 1
            assert result.results[0].status == "applied"
            assert result.results[0].server_version == 6

    @pytest.mark.asyncio
    async def test_apply_changes_summary_conflict(self, sync_service):
        """Test applying summary changes with version conflict."""
        now = datetime.now(UTC)
        session_payload = {
            "session_id": "test-session",
            "user_id": 123,
            "client_id": "test-client",
            "expires_at": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        }

        from app.api.models.requests import SyncApplyItem

        changes = [
            SyncApplyItem(
                entity_type="summary",
                id=1,
                action="update",
                last_seen_version=5,
                payload={"is_read": True},
            )
        ]

        sync_service._summary_repo.async_get_summary_for_sync_apply = AsyncMock(
            return_value={
                "id": 1,
                "server_version": 10,  # Newer version
                "is_read": True,
            }
        )

        with patch.object(
            sync_service, "_load_session", new_callable=AsyncMock, return_value=session_payload
        ):
            result = await sync_service.apply_changes(
                session_id="test-session", user_id=123, client_id="test-client", changes=changes
            )

            assert len(result.results) == 1
            assert result.results[0].status == "conflict"
            assert result.results[0].server_version == 10
            assert result.results[0].error_code == "CONFLICT_VERSION"
            assert result.conflicts is not None
            assert len(result.conflicts) == 1


class TestApplySummaryChange:
    """Test _apply_summary_change method."""

    @pytest.mark.asyncio
    async def test_apply_summary_invalid_id(self, sync_service):
        """Test applying change with invalid ID."""
        from app.api.models.requests import SyncApplyItem

        change = SyncApplyItem(
            entity_type="summary", id="invalid", action="update", last_seen_version=5, payload={}
        )

        result = await sync_service._apply_summary_change(change, 123)

        assert result.status == "invalid"
        assert result.error_code == "INVALID_ID"

    @pytest.mark.asyncio
    async def test_apply_summary_not_found(self, sync_service):
        """Test applying change when summary not found."""
        from app.api.models.requests import SyncApplyItem

        change = SyncApplyItem(
            entity_type="summary", id=999, action="update", last_seen_version=5, payload={}
        )

        sync_service._summary_repo.async_get_summary_for_sync_apply = AsyncMock(return_value=None)

        result = await sync_service._apply_summary_change(change, 123)

        assert result.status == "invalid"
        assert result.error_code == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_apply_summary_invalid_fields(self, sync_service):
        """Test applying change with invalid fields."""
        from app.api.models.requests import SyncApplyItem

        change = SyncApplyItem(
            entity_type="summary",
            id=1,
            action="update",
            last_seen_version=5,
            payload={"invalid_field": "value"},
        )

        sync_service._summary_repo.async_get_summary_for_sync_apply = AsyncMock(
            return_value={"id": 1, "server_version": 5}
        )

        result = await sync_service._apply_summary_change(change, 123)

        assert result.status == "invalid"
        assert result.error_code == "INVALID_FIELDS"

    @pytest.mark.asyncio
    async def test_apply_summary_delete_action(self, sync_service):
        """Test applying delete action."""
        from app.api.models.requests import SyncApplyItem

        change = SyncApplyItem(
            entity_type="summary", id=1, action="delete", last_seen_version=5, payload=None
        )

        sync_service._summary_repo.async_get_summary_for_sync_apply = AsyncMock(
            return_value={"id": 1, "server_version": 5}
        )
        sync_service._summary_repo.async_apply_sync_change = AsyncMock(return_value=6)

        result = await sync_service._apply_summary_change(change, 123)

        assert result.status == "applied"
        assert result.server_version == 6

        # Verify delete was called
        call_kwargs = sync_service._summary_repo.async_apply_sync_change.call_args[1]
        assert call_kwargs["is_deleted"] is True
        assert call_kwargs["deleted_at"] is not None

    @pytest.mark.asyncio
    async def test_apply_summary_update_is_read(self, sync_service):
        """Test updating is_read field."""
        from app.api.models.requests import SyncApplyItem

        change = SyncApplyItem(
            entity_type="summary",
            id=1,
            action="update",
            last_seen_version=5,
            payload={"is_read": True},
        )

        sync_service._summary_repo.async_get_summary_for_sync_apply = AsyncMock(
            return_value={"id": 1, "server_version": 5}
        )
        sync_service._summary_repo.async_apply_sync_change = AsyncMock(return_value=6)

        result = await sync_service._apply_summary_change(change, 123)

        assert result.status == "applied"

        # Verify is_read was updated
        call_kwargs = sync_service._summary_repo.async_apply_sync_change.call_args[1]
        assert call_kwargs["is_read"] is True


class TestSerializationEdgeCases:
    """Test serialization edge cases for different entity types."""

    def test_serialize_request_deleted(self, sync_service):
        """Test serializing deleted request."""
        now = datetime.now(UTC)
        request_dict = {
            "id": "req-1",
            "type": "url",
            "server_version": 10,
            "is_deleted": True,
            "deleted_at": now,
            "updated_at": now,
        }

        envelope = sync_service._serialize_request(request_dict)

        assert envelope.entity_type == "request"
        assert envelope.request is None
        assert envelope.deleted_at is not None

    def test_serialize_summary_deleted(self, sync_service):
        """Test serializing deleted summary."""
        now = datetime.now(UTC)
        summary_dict = {
            "id": 1,
            "request": 1,
            "server_version": 10,
            "is_deleted": True,
            "deleted_at": now,
            "updated_at": now,
        }

        envelope = sync_service._serialize_summary(summary_dict)

        assert envelope.entity_type == "summary"
        assert envelope.summary is None
        assert envelope.deleted_at is not None

    def test_serialize_summary_request_as_none(self, sync_service):
        """Test serializing summary when request is None."""
        summary_dict = {
            "id": 1,
            "request": None,
            "lang": "en",
            "is_read": False,
            "server_version": 10,
            "is_deleted": False,
            "created_at": None,
            "updated_at": None,
        }

        envelope = sync_service._serialize_summary(summary_dict)

        assert envelope.summary["request_id"] is None

    def test_serialize_crawl_result_deleted(self, sync_service):
        """Test serializing deleted crawl result."""
        now = datetime.now(UTC)
        crawl_dict = {
            "id": 1,
            "request": 1,
            "server_version": 10,
            "is_deleted": True,
            "deleted_at": now,
            "updated_at": now,
        }

        envelope = sync_service._serialize_crawl_result(crawl_dict)

        assert envelope.entity_type == "crawl_result"
        assert envelope.crawl_result is None
        assert envelope.deleted_at is not None

    def test_serialize_crawl_result_request_as_dict(self, sync_service):
        """Test serializing crawl result with request as dict."""
        crawl_dict = {
            "id": 1,
            "request": {"id": 42, "type": "url"},
            "source_url": "http://test.com",
            "endpoint": "firecrawl",
            "server_version": 10,
            "is_deleted": False,
            "updated_at": None,
        }

        envelope = sync_service._serialize_crawl_result(crawl_dict)

        assert envelope.crawl_result["request_id"] == 42

    def test_serialize_llm_call_deleted(self, sync_service):
        """Test serializing deleted LLM call."""
        now = datetime.now(UTC)
        call_dict = {
            "id": 1,
            "request": 1,
            "server_version": 10,
            "is_deleted": True,
            "deleted_at": now,
            "created_at": now,
            "updated_at": now,
        }

        envelope = sync_service._serialize_llm_call(call_dict)

        assert envelope.entity_type == "llm_call"
        assert envelope.llm_call is None
        assert envelope.deleted_at is not None

    def test_serialize_llm_call_request_as_dict(self, sync_service):
        """Test serializing LLM call with request as dict."""
        call_dict = {
            "id": 1,
            "request": {"id": 42, "type": "url"},
            "provider": "openrouter",
            "model": "gpt-4",
            "status": "completed",
            "server_version": 10,
            "is_deleted": False,
            "created_at": None,
            "updated_at": None,
        }

        envelope = sync_service._serialize_llm_call(call_dict)

        assert envelope.llm_call["request_id"] == 42


class TestBuildResponses:
    """Test _build_full and _build_delta methods."""

    def test_build_full_response(self, sync_service):
        """Test building full sync response."""
        records = [make_sync_envelope(entity_id=i, server_version=i) for i in range(1, 4)]

        response = sync_service._build_full(
            session_id="test-session", records=records, has_more=False, next_since=3, limit=100
        )

        assert response.session_id == "test-session"
        assert len(response.items) == 3
        assert response.has_more is False
        assert response.next_since == 3
        assert response.pagination.total == 3
        assert response.pagination.limit == 100

    def test_build_delta_response(self, sync_service):
        """Test building delta sync response."""
        now = datetime.now(UTC)
        records = [
            make_sync_envelope(entity_id=5, server_version=5, deleted_at=None),
            make_sync_envelope(entity_id=6, server_version=6, deleted_at=now.isoformat() + "Z"),
        ]

        response = sync_service._build_delta(
            session_id="test-session",
            since=4,
            records=records,
            has_more=False,
            next_since=6,
            limit=100,
        )

        assert response.session_id == "test-session"
        assert response.since == 4
        assert len(response.created) == 1
        assert len(response.updated) == 0
        assert len(response.deleted) == 1


class TestCoerceIsoEdgeCases:
    """Additional edge cases for _coerce_iso."""

    def test_coerce_iso_with_string_datetime(self, sync_service):
        """Test with datetime that is actually a string object."""
        # This tests the isinstance(dt_value, str) branch
        result = sync_service._coerce_iso("2024-01-15T10:30:00+00:00")
        assert "2024-01-15T10:30:00" in result
        assert result.endswith("Z")

    def test_coerce_iso_with_malformed_string(self, sync_service):
        """Test with completely malformed string."""
        result = sync_service._coerce_iso("not a datetime at all!!!")
        # Should fallback to current time
        assert "T" in result
        assert result.endswith("Z")

    def test_coerce_iso_with_numeric_value(self, sync_service):
        """Test with numeric value (edge case)."""
        result = sync_service._coerce_iso(12345)
        # Should fallback to current time
        assert "T" in result
        assert result.endswith("Z")
