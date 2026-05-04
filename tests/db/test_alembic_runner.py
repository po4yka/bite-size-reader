"""Tests for app.db.alembic_runner — upgrade_to_head and cohabitation logic."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def _get_alembic_version(db_path: str) -> str | None:
    """Return the current alembic_version value, or None if table absent."""
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'"
        ).fetchone()
        if not row:
            return None
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        return row[0] if row else None


def _seed_legacy_migration_history(db_path: str, migrations: list[str]) -> None:
    """Pre-populate migration_history as the old MigrationRunner would."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS migration_history (
                migration_name TEXT PRIMARY KEY,
                applied_at DATETIME,
                rollback_sql TEXT
            )
        """)
        for name in migrations:
            conn.execute(
                "INSERT OR IGNORE INTO migration_history (migration_name, applied_at) VALUES (?, datetime('now'))",
                (name,),
            )


def _create_peewee_tables(db_path: str) -> None:
    """Create all app tables via Peewee, mirroring the production bootstrap order.

    In production, DatabaseBootstrapService.migrate() calls create_tables(ALL_MODELS,
    safe=True) *before* upgrade_to_head().  Revisions that alter existing tables
    (e.g. 0003 llm_calls reconstruction, 0005-0016 ADD COLUMN) depend on those
    tables already existing.

    Must initialize database_proxy first (same as bootstrap.initialize_database_proxy)
    because BaseModel._meta.database points to the proxy, which bind_ctx alone cannot
    satisfy for internal schema operations (_schema.database).
    """
    import peewee

    from app.db.models import ALL_MODELS, database_proxy

    db = peewee.SqliteDatabase(db_path)
    database_proxy.initialize(db)
    with db.connection_context(), db.bind_ctx(ALL_MODELS):
        db.create_tables(ALL_MODELS, safe=True)
    db.close()


class TestUpgradeToHeadFreshDb:
    """Fresh database seeded by Peewee — Alembic should run through to head."""

    def test_alembic_version_populated(self, tmp_path: Path) -> None:
        from app.db.alembic_runner import upgrade_to_head

        db_path = str(tmp_path / "fresh.db")
        _create_peewee_tables(db_path)
        upgrade_to_head(db_path)
        version = _get_alembic_version(db_path)
        assert version == "0016", f"expected head=0016, got {version!r}"

    def test_migration_history_absent(self, tmp_path: Path) -> None:
        from app.db.alembic_runner import upgrade_to_head

        db_path = str(tmp_path / "fresh.db")
        _create_peewee_tables(db_path)
        upgrade_to_head(db_path)
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='migration_history'"
            ).fetchone()
        assert row is None, "migration_history should not be created by Alembic"

    def test_idempotent_second_call(self, tmp_path: Path) -> None:
        from app.db.alembic_runner import upgrade_to_head

        db_path = str(tmp_path / "fresh.db")
        _create_peewee_tables(db_path)
        upgrade_to_head(db_path)
        v1 = _get_alembic_version(db_path)
        upgrade_to_head(db_path)
        v2 = _get_alembic_version(db_path)
        assert v1 == v2 == "0016"


class TestUpgradeToHeadLegacyDb:
    """Database that already has migration_history — should auto-stamp without re-running."""

    _LEGACY_MIGRATIONS = [
        "001_add_performance_indexes",
        "002_add_schema_constraints",
        "003_add_user_preferences",
        "004_migrate_summary_embeddings_to_chroma",
        "005_add_schema_columns",
        "006_migrate_legacy_payloads",
        "007_add_attachment_processing",
        "008_add_request_error_fields",
        "009_add_digest_indexes",
        "010_add_request_error_context",
        "011_add_channel_metadata",
        "012_add_channel_categories",
        "013_add_reading_position",
        "014_add_bot_reply_message_id",
        "015_add_signal_sources",
    ]

    def test_stamp_applied_no_revisions_run(self, tmp_path: Path) -> None:
        from app.db.alembic_runner import upgrade_to_head

        db_path = str(tmp_path / "legacy.db")
        # Simulate a legacy DB: migration_history exists, but no alembic_version
        _seed_legacy_migration_history(db_path, self._LEGACY_MIGRATIONS)
        assert _get_alembic_version(db_path) is None

        upgrade_to_head(db_path)
        version = _get_alembic_version(db_path)
        assert version == "0016", f"expected stamp to head=0016, got {version!r}"

    def test_idempotent_on_already_stamped_db(self, tmp_path: Path) -> None:
        from app.db.alembic_runner import upgrade_to_head

        db_path = str(tmp_path / "legacy.db")
        _seed_legacy_migration_history(db_path, self._LEGACY_MIGRATIONS)
        upgrade_to_head(db_path)
        v1 = _get_alembic_version(db_path)
        # Second call: alembic_version exists, stamp branch must NOT fire again
        upgrade_to_head(db_path)
        v2 = _get_alembic_version(db_path)
        assert v1 == v2 == "0016"

    def test_migration_history_preserved(self, tmp_path: Path) -> None:
        from app.db.alembic_runner import upgrade_to_head

        db_path = str(tmp_path / "legacy.db")
        _seed_legacy_migration_history(db_path, self._LEGACY_MIGRATIONS)
        upgrade_to_head(db_path)
        # Legacy table must not be dropped by upgrade_to_head (Phase 5 does that)
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='migration_history'"
            ).fetchone()
        assert row is not None, "migration_history must survive upgrade_to_head"


class TestHelpers:
    def test_has_legacy_migration_history_empty_db(self, tmp_path: Path) -> None:
        from app.db.alembic_runner import _has_legacy_migration_history

        db_path = str(tmp_path / "empty.db")
        sqlite3.connect(db_path).close()
        assert _has_legacy_migration_history(db_path) is False

    def test_has_legacy_migration_history_table_without_rows(self, tmp_path: Path) -> None:
        from app.db.alembic_runner import _has_legacy_migration_history

        db_path = str(tmp_path / "empty_table.db")
        _seed_legacy_migration_history(db_path, [])
        assert _has_legacy_migration_history(db_path) is False

    def test_has_legacy_migration_history_with_rows(self, tmp_path: Path) -> None:
        from app.db.alembic_runner import _has_legacy_migration_history

        db_path = str(tmp_path / "with_rows.db")
        _seed_legacy_migration_history(db_path, ["001_foo"])
        assert _has_legacy_migration_history(db_path) is True

    def test_has_alembic_version_missing(self, tmp_path: Path) -> None:
        from app.db.alembic_runner import _has_alembic_version

        db_path = str(tmp_path / "no_alembic.db")
        sqlite3.connect(db_path).close()
        assert _has_alembic_version(db_path) is False

    def test_has_alembic_version_present(self, tmp_path: Path) -> None:
        from app.db.alembic_runner import _has_alembic_version, upgrade_to_head

        db_path = str(tmp_path / "alembic.db")
        _create_peewee_tables(db_path)
        upgrade_to_head(db_path)
        assert _has_alembic_version(db_path) is True

    def test_memory_db_never_has_legacy(self) -> None:
        from app.db.alembic_runner import _has_legacy_migration_history

        assert _has_legacy_migration_history(":memory:") is False
