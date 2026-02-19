"""Tests for DigestAPIService."""

from __future__ import annotations

import pytest

from app.api.exceptions import FeatureDisabledError, ValidationError
from app.config.digest import ChannelDigestConfig
from app.db.models import (
    ALL_MODELS,
    Channel,
    ChannelSubscription,
    DigestDelivery,
    User,
    _utcnow,
)


@pytest.fixture
def db_setup(tmp_path):
    """Set up an in-memory test database with test user."""
    import peewee

    db = peewee.SqliteDatabase(":memory:")
    with db.bind_ctx(ALL_MODELS):
        db.create_tables(ALL_MODELS)
        user = User.create(telegram_id=123456789, username="testuser")
        yield db, user
        db.close()


@pytest.fixture
def enabled_config():
    """Digest config with feature enabled."""
    return ChannelDigestConfig(DIGEST_ENABLED=True, DIGEST_MAX_CHANNELS=5)


@pytest.fixture
def disabled_config():
    """Digest config with feature disabled."""
    return ChannelDigestConfig(DIGEST_ENABLED=False)


@pytest.fixture
def service(enabled_config):
    from app.api.services.digest_api_service import DigestAPIService

    return DigestAPIService(enabled_config)


class TestListSubscriptions:
    def test_empty_list(self, db_setup, service):
        db, user = db_setup
        with db.bind_ctx(ALL_MODELS):
            result = service.list_subscriptions(user.telegram_id)
            assert result["channels"] == []
            assert result["active_count"] == 0
            assert result["max_channels"] is None
            assert result["unlimited_channels"] is True

    def test_with_subscriptions(self, db_setup, service):
        db, user = db_setup
        with db.bind_ctx(ALL_MODELS):
            ch = Channel.create(username="testchannel", title="Test Channel", is_active=True)
            ChannelSubscription.create(user=user.telegram_id, channel=ch, is_active=True)

            result = service.list_subscriptions(user.telegram_id)
            assert result["active_count"] == 1
            assert len(result["channels"]) == 1
            assert result["channels"][0].username == "testchannel"

    def test_feature_disabled(self, db_setup, disabled_config):
        from app.api.services.digest_api_service import DigestAPIService

        db, user = db_setup
        svc = DigestAPIService(disabled_config)
        with db.bind_ctx(ALL_MODELS):
            with pytest.raises(FeatureDisabledError):
                svc.list_subscriptions(user.telegram_id)


class TestSubscribe:
    def test_subscribe_new_channel(self, db_setup, service):
        db, user = db_setup
        with db.bind_ctx(ALL_MODELS):
            result = service.subscribe_channel(user.telegram_id, "newchannel")
            assert result["status"] == "created"
            assert result["username"] == "newchannel"

    def test_subscribe_already_subscribed(self, db_setup, service):
        db, user = db_setup
        with db.bind_ctx(ALL_MODELS):
            service.subscribe_channel(user.telegram_id, "testchan")
            result = service.subscribe_channel(user.telegram_id, "testchan")
            assert result["status"] == "already_subscribed"

    def test_subscribe_reactivate(self, db_setup, service):
        db, user = db_setup
        with db.bind_ctx(ALL_MODELS):
            service.subscribe_channel(user.telegram_id, "testchan")
            service.unsubscribe_channel(user.telegram_id, "testchan")
            result = service.subscribe_channel(user.telegram_id, "testchan")
            assert result["status"] == "reactivated"

    def test_subscribe_not_limited_by_max_channels_config(self, db_setup):
        from app.api.services.digest_api_service import DigestAPIService

        cfg = ChannelDigestConfig(DIGEST_ENABLED=True, DIGEST_MAX_CHANNELS=1)
        svc = DigestAPIService(cfg)
        db, user = db_setup
        with db.bind_ctx(ALL_MODELS):
            svc.subscribe_channel(user.telegram_id, "chan01")
            result = svc.subscribe_channel(user.telegram_id, "chan02")
            assert result["status"] == "created"
            assert result["username"] == "chan02"

    def test_subscribe_invalid_username(self, db_setup, service):
        db, user = db_setup
        with db.bind_ctx(ALL_MODELS):
            with pytest.raises(ValidationError, match="Invalid"):
                service.subscribe_channel(user.telegram_id, "x")


class TestUnsubscribe:
    def test_unsubscribe_success(self, db_setup, service):
        db, user = db_setup
        with db.bind_ctx(ALL_MODELS):
            service.subscribe_channel(user.telegram_id, "testchan")
            result = service.unsubscribe_channel(user.telegram_id, "testchan")
            assert result["status"] == "unsubscribed"

    def test_unsubscribe_not_found(self, db_setup, service):
        db, user = db_setup
        with db.bind_ctx(ALL_MODELS):
            with pytest.raises(ValidationError, match="not found"):
                service.unsubscribe_channel(user.telegram_id, "nonexistent")

    def test_unsubscribe_not_subscribed(self, db_setup, service):
        db, user = db_setup
        with db.bind_ctx(ALL_MODELS):
            Channel.create(username="orphan", title="orphan", is_active=True)
            with pytest.raises(ValidationError, match="Not subscribed"):
                service.unsubscribe_channel(user.telegram_id, "orphan")


class TestPreferences:
    def test_get_global_defaults(self, db_setup, service):
        db, user = db_setup
        with db.bind_ctx(ALL_MODELS):
            prefs = service.get_preferences(user.telegram_id)
            assert prefs.delivery_time == "10:00,19:00"
            assert prefs.delivery_time_source == "global"
            assert prefs.timezone_source == "global"

    def test_update_and_get(self, db_setup, service):
        db, user = db_setup
        with db.bind_ctx(ALL_MODELS):
            prefs = service.update_preferences(
                user.telegram_id,
                delivery_time="14:00",
                timezone="Europe/Moscow",
            )
            assert prefs.delivery_time == "14:00"
            assert prefs.delivery_time_source == "user"
            assert prefs.timezone == "Europe/Moscow"
            assert prefs.timezone_source == "user"
            # Unchanged fields still use global
            assert prefs.hours_lookback_source == "global"

    def test_update_invalid_time(self, db_setup, service):
        db, user = db_setup
        with db.bind_ctx(ALL_MODELS):
            with pytest.raises(ValidationError, match="HH:MM"):
                service.update_preferences(user.telegram_id, delivery_time="invalid")


class TestDeliveries:
    def test_empty_history(self, db_setup, service):
        db, user = db_setup
        with db.bind_ctx(ALL_MODELS):
            result = service.list_deliveries(user.telegram_id)
            assert result["deliveries"] == []
            assert result["total"] == 0

    def test_paginated_history(self, db_setup, service):
        db, user = db_setup
        with db.bind_ctx(ALL_MODELS):
            for i in range(5):
                DigestDelivery.create(
                    user=user.telegram_id,
                    post_count=i + 1,
                    channel_count=2,
                    digest_type="scheduled",
                    delivered_at=_utcnow(),
                )

            result = service.list_deliveries(user.telegram_id, limit=2, offset=0)
            assert len(result["deliveries"]) == 2
            assert result["total"] == 5


class TestTriggerDigest:
    def test_trigger_no_subscriptions(self, db_setup, service):
        db, user = db_setup
        with db.bind_ctx(ALL_MODELS):
            with pytest.raises(ValidationError, match="No active"):
                service.trigger_digest(user.telegram_id)

    def test_trigger_success(self, db_setup, service):
        db, user = db_setup
        with db.bind_ctx(ALL_MODELS):
            ch = Channel.create(username="testch", title="Test", is_active=True)
            ChannelSubscription.create(user=user.telegram_id, channel=ch, is_active=True)

            result = service.trigger_digest(user.telegram_id)
            assert result.status == "queued"
            assert result.correlation_id
