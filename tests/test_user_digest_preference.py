"""Tests for UserDigestPreference model CRUD and global fallback merge."""

from __future__ import annotations

import pytest

from app.db.models import ALL_MODELS, User, UserDigestPreference, _utcnow


@pytest.fixture
def db_setup(tmp_path):
    """Set up an in-memory test database."""
    import peewee

    db = peewee.SqliteDatabase(":memory:")

    # Bind all models to test database
    with db.bind_ctx(ALL_MODELS):
        db.create_tables(ALL_MODELS)
        # Create test user
        user = User.create(
            telegram_id=123456789,
            username="testuser",
        )
        yield db, user
        db.close()


class TestUserDigestPreference:
    def test_create_preference(self, db_setup):
        db, user = db_setup
        with db.bind_ctx(ALL_MODELS):
            pref = UserDigestPreference.create(
                user=user,
                delivery_time="10:30",
                timezone="Europe/Moscow",
                hours_lookback=48,
                max_posts_per_digest=30,
                min_relevance_score=0.5,
            )
            assert pref.id is not None
            assert pref.delivery_time == "10:30"
            assert pref.timezone == "Europe/Moscow"
            assert pref.hours_lookback == 48
            assert pref.max_posts_per_digest == 30
            assert pref.min_relevance_score == 0.5

    def test_null_fields_for_global_fallback(self, db_setup):
        db, user = db_setup
        with db.bind_ctx(ALL_MODELS):
            pref = UserDigestPreference.create(user=user)
            assert pref.delivery_time is None
            assert pref.timezone is None
            assert pref.hours_lookback is None
            assert pref.max_posts_per_digest is None
            assert pref.min_relevance_score is None

    def test_unique_user_constraint(self, db_setup):
        import peewee

        db, user = db_setup
        with db.bind_ctx(ALL_MODELS):
            UserDigestPreference.create(user=user)
            with pytest.raises(peewee.IntegrityError):
                UserDigestPreference.create(user=user)

    def test_update_preference(self, db_setup):
        db, user = db_setup
        with db.bind_ctx(ALL_MODELS):
            pref = UserDigestPreference.create(user=user, hours_lookback=24)
            pref.hours_lookback = 72
            pref.updated_at = _utcnow()
            pref.save()

            reloaded = UserDigestPreference.get_by_id(pref.id)
            assert reloaded.hours_lookback == 72

    def test_get_or_create(self, db_setup):
        db, user = db_setup
        with db.bind_ctx(ALL_MODELS):
            pref, created = UserDigestPreference.get_or_create(
                user=user,
                defaults={"delivery_time": "08:00"},
            )
            assert created is True
            assert pref.delivery_time == "08:00"

            pref2, created2 = UserDigestPreference.get_or_create(
                user=user,
                defaults={"delivery_time": "09:00"},
            )
            assert created2 is False
            assert pref2.delivery_time == "08:00"  # Original value preserved

    def test_model_in_all_models(self):
        assert UserDigestPreference in ALL_MODELS

    def test_cascade_delete(self, db_setup):
        db, user = db_setup
        with db.bind_ctx(ALL_MODELS):
            db.execute_sql("PRAGMA foreign_keys = ON")
            UserDigestPreference.create(user=user, delivery_time="10:00")
            assert UserDigestPreference.select().count() == 1

            user.delete_instance()
            assert UserDigestPreference.select().count() == 0
