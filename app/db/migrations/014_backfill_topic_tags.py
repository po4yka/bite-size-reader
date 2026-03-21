"""Backfill topic_tags from summary JSON payloads into tags and summary_tags tables."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import peewee

from app.core.logging_utils import get_logger, log_exception

if TYPE_CHECKING:
    from app.db.session import DatabaseSessionManager

logger = get_logger(__name__)

_BATCH_LOG_INTERVAL = 100


def _normalize_tag_name(name: str) -> str:
    """Inline copy of tag_service.normalize_tag_name to keep migration self-contained."""
    return " ".join(name.lower().strip().split())


def upgrade(db: DatabaseSessionManager) -> None:
    """Backfill topic_tags from summary JSON into tags and summary_tags tables."""
    database = db._database

    # Fetch all summaries joined with requests to get user_id.
    # Only include summaries where json_payload is not null.
    rows = database.execute_sql(
        """
        SELECT s.id, s.json_payload, r.user_id
        FROM summaries s
        JOIN requests r ON r.id = s.request_id
        WHERE s.json_payload IS NOT NULL
          AND r.user_id IS NOT NULL
        """
    ).fetchall()

    total = len(rows)
    logger.info("backfill_topic_tags_start", extra={"total_summaries": total})

    if total == 0:
        logger.info("backfill_topic_tags_nothing_to_do")
        return

    tags_created = 0
    summary_tags_created = 0
    skipped = 0

    with database.atomic():
        for idx, (summary_id, json_payload_raw, user_id) in enumerate(rows, 1):
            # Parse json_payload -- it may already be a dict (JSONField) or a string
            if isinstance(json_payload_raw, str):
                try:
                    payload = json.loads(json_payload_raw)
                except (json.JSONDecodeError, TypeError):
                    skipped += 1
                    continue
            elif isinstance(json_payload_raw, dict):
                payload = json_payload_raw
            else:
                skipped += 1
                continue

            if not isinstance(payload, dict):
                skipped += 1
                continue

            topic_tags = payload.get("topic_tags")
            if not topic_tags or not isinstance(topic_tags, list):
                continue

            for raw_tag in topic_tags:
                if not isinstance(raw_tag, str):
                    continue

                normalized = _normalize_tag_name(raw_tag)
                if not normalized:
                    continue

                # Find or create Tag for (user_id, normalized_name)
                tag_row = database.execute_sql(
                    "SELECT id FROM tags WHERE user_id = ? AND normalized_name = ?",
                    (user_id, normalized),
                ).fetchone()

                if tag_row:
                    tag_id = tag_row[0]
                else:
                    now = database.execute_sql("SELECT datetime('now')").fetchone()[0]
                    cursor = database.execute_sql(
                        """
                        INSERT INTO tags (user_id, name, normalized_name, color,
                                          server_version, is_deleted, updated_at, created_at)
                        VALUES (?, ?, ?, NULL,
                                CAST(strftime('%%s', 'now') * 1000 AS INTEGER), 0, ?, ?)
                        """,
                        (user_id, raw_tag.strip(), normalized, now, now),
                    )
                    tag_id = cursor.lastrowid
                    tags_created += 1

                # Create SummaryTag -- skip if already exists
                try:
                    database.execute_sql(
                        """
                        INSERT OR IGNORE INTO summary_tags
                            (summary_id, tag_id, source, server_version, created_at)
                        VALUES (?, ?, 'ai',
                                CAST(strftime('%%s', 'now') * 1000 AS INTEGER),
                                datetime('now'))
                        """,
                        (summary_id, tag_id),
                    )
                    # rowcount is not reliable with INSERT OR IGNORE on all drivers,
                    # so we count optimistically
                    summary_tags_created += 1
                except peewee.DatabaseError:
                    pass  # duplicate -- already linked

            if idx % _BATCH_LOG_INTERVAL == 0:
                logger.info(
                    "backfill_topic_tags_progress",
                    extra={
                        "processed": idx,
                        "total": total,
                        "tags_created": tags_created,
                        "summary_tags_created": summary_tags_created,
                    },
                )

    logger.info(
        "backfill_topic_tags_complete",
        extra={
            "total_summaries": total,
            "skipped": skipped,
            "tags_created": tags_created,
            "summary_tags_created": summary_tags_created,
        },
    )


def downgrade(db: DatabaseSessionManager) -> None:
    """Remove AI-generated tags created by backfill."""
    database = db._database

    try:
        # Remove AI-sourced summary_tags
        database.execute_sql("DELETE FROM summary_tags WHERE source = 'ai'")
        logger.info("backfill_ai_summary_tags_deleted")

        # Remove orphaned tags (tags not referenced by any summary_tag)
        database.execute_sql(
            """
            DELETE FROM tags
            WHERE id NOT IN (SELECT DISTINCT tag_id FROM summary_tags)
            """
        )
        logger.info("backfill_orphaned_tags_deleted")
    except peewee.DatabaseError as e:
        log_exception(logger, "backfill_downgrade_failed", e)
        raise

    logger.info("migration_014_downgrade_complete")
