"""Tests for app/cli/add_performance_indexes.py."""

from __future__ import annotations

from app.cli.add_performance_indexes import create_indexes
from tests.integration.helpers import temp_db


def test_create_indexes_is_idempotent() -> None:
    """create_indexes() must succeed when run twice (IF NOT EXISTS semantics)."""
    with temp_db() as db:
        create_indexes(db)
        # Second call must not raise even though indexes already exist
        create_indexes(db)


def test_create_indexes_produces_expected_index_names() -> None:
    """All seven expected indexes should be present after create_indexes()."""
    expected = {
        "idx_requests_user_id",
        "idx_requests_status",
        "idx_requests_created_at",
        "idx_requests_user_created",
        "idx_summaries_is_read",
        "idx_summaries_lang",
        "idx_summaries_created_at",
    }

    with temp_db() as db:
        create_indexes(db)

        with db.connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
            ).fetchall()

        names = {row[0] for row in rows}
        assert expected <= names, f"Missing indexes: {expected - names}"
