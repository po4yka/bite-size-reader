from __future__ import annotations

import pytest

from app.db.database import Database


@pytest.fixture()
def db(tmp_path) -> Database:
    path = tmp_path / "app.db"
    database = Database(str(path))
    database.migrate()
    with database.connect() as conn:
        conn.execute(
            """
            CREATE TABLE user_interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                response_sent INTEGER,
                response_type TEXT,
                error_occurred INTEGER,
                error_message TEXT,
                processing_time_ms INTEGER,
                request_id INTEGER
            )
            """
        )
        conn.commit()
    return database


def _insert_interaction(db: Database) -> int:
    with db.connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO user_interactions (
                response_sent,
                response_type,
                error_occurred,
                error_message,
                processing_time_ms,
                request_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (0, "initial", 1, "pending", 250, 7),
        )
        conn.commit()
        return int(cur.lastrowid)


def test_update_user_interaction_updates_allowed_fields(db: Database) -> None:
    interaction_id = _insert_interaction(db)

    db.update_user_interaction(
        interaction_id=interaction_id,
        updates={
            "response_sent": True,
            "response_type": "summary",
            "error_occurred": False,
            "error_message": None,
            "processing_time_ms": 1234,
            "request_id": 42,
        },
    )

    row = db.fetchone("SELECT * FROM user_interactions WHERE id = ?", (interaction_id,))
    assert row is not None
    assert row["response_sent"] == 1
    assert row["response_type"] == "summary"
    assert row["error_occurred"] == 0
    assert row["error_message"] is None
    assert row["processing_time_ms"] == 1234
    assert row["request_id"] == 42


def test_update_user_interaction_rejects_unknown_field(db: Database) -> None:
    interaction_id = _insert_interaction(db)

    with pytest.raises(ValueError):
        db.update_user_interaction(interaction_id=interaction_id, updates={"invalid": "noop"})


def test_update_user_interaction_ignores_empty_updates(db: Database) -> None:
    interaction_id = _insert_interaction(db)
    before = db.fetchone("SELECT * FROM user_interactions WHERE id = ?", (interaction_id,))
    assert before is not None

    db.update_user_interaction(interaction_id=interaction_id, updates={})

    after = db.fetchone("SELECT * FROM user_interactions WHERE id = ?", (interaction_id,))
    assert after is not None
    assert dict(after) == dict(before)
