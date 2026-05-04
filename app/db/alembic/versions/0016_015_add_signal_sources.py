"""Add generic signal-source tables and backfill from legacy RSS/channel tables.

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-04
"""

from __future__ import annotations

import json
import logging

from alembic import op
from sqlalchemy import text

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | None = None
depends_on: str | None = None

logger = logging.getLogger(__name__)

_CREATE_SOURCES = """
CREATE TABLE IF NOT EXISTS sources (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    kind                TEXT NOT NULL,
    external_id         TEXT,
    url                 TEXT,
    title               TEXT,
    description         TEXT,
    site_url            TEXT,
    is_active           INTEGER NOT NULL DEFAULT 1,
    fetch_error_count   INTEGER NOT NULL DEFAULT 0,
    last_error          TEXT,
    last_fetched_at     DATETIME,
    last_successful_at  DATETIME,
    metadata_json       TEXT,
    legacy_rss_feed_id  INTEGER REFERENCES rss_feeds(id) ON DELETE SET NULL,
    legacy_channel_id   INTEGER REFERENCES channels(id) ON DELETE SET NULL,
    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(kind, external_id),
    UNIQUE(legacy_rss_feed_id),
    UNIQUE(legacy_channel_id)
)
"""

_CREATE_SUBSCRIPTIONS = """
CREATE TABLE IF NOT EXISTS subscriptions (
    id                              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                         INTEGER NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
    source_id                       INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    is_active                       INTEGER NOT NULL DEFAULT 1,
    cadence_seconds                 INTEGER,
    next_fetch_at                   DATETIME,
    topic_constraints_json          TEXT,
    metadata_json                   TEXT,
    legacy_rss_subscription_id      INTEGER UNIQUE REFERENCES rss_feed_subscriptions(id) ON DELETE SET NULL,
    legacy_channel_subscription_id  INTEGER UNIQUE,
    updated_at                      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at                      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, source_id)
)
"""

_CREATE_FEED_ITEMS = """
CREATE TABLE IF NOT EXISTS feed_items (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id               INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    external_id             TEXT NOT NULL,
    canonical_url           TEXT,
    title                   TEXT,
    content_text            TEXT,
    author                  TEXT,
    published_at            DATETIME,
    views                   INTEGER,
    forwards                INTEGER,
    comments                INTEGER,
    engagement_score        REAL,
    metadata_json           TEXT,
    legacy_rss_item_id      INTEGER UNIQUE REFERENCES rss_feed_items(id) ON DELETE SET NULL,
    legacy_channel_post_id  INTEGER UNIQUE REFERENCES channel_posts(id) ON DELETE SET NULL,
    updated_at              DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at              DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_id, external_id)
)
"""

_CREATE_TOPICS = """
CREATE TABLE IF NOT EXISTS topics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    description   TEXT,
    weight        REAL NOT NULL DEFAULT 1.0,
    embedding_ref TEXT,
    metadata_json TEXT,
    is_active     INTEGER NOT NULL DEFAULT 1,
    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, name)
)
"""

_CREATE_USER_SIGNALS = """
CREATE TABLE IF NOT EXISTS user_signals (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL REFERENCES users(telegram_user_id) ON DELETE CASCADE,
    feed_item_id     INTEGER NOT NULL REFERENCES feed_items(id) ON DELETE CASCADE,
    topic_id         INTEGER REFERENCES topics(id) ON DELETE SET NULL,
    status           TEXT NOT NULL DEFAULT 'candidate',
    heuristic_score  REAL,
    llm_score        REAL,
    final_score      REAL,
    filter_stage     TEXT NOT NULL DEFAULT 'heuristic',
    evidence_json    TEXT,
    llm_judge_json   TEXT,
    llm_cost_usd     REAL,
    decided_at       DATETIME,
    updated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, feed_item_id)
)
"""


def upgrade() -> None:
    conn = op.get_bind()
    for ddl in (_CREATE_SOURCES, _CREATE_SUBSCRIPTIONS, _CREATE_FEED_ITEMS,
                _CREATE_TOPICS, _CREATE_USER_SIGNALS):
        op.execute(text(ddl))

    tables = {
        row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    }

    # Backfill RSS sources
    rss_sources = 0
    if "rss_feeds" in tables:
        feeds = conn.execute(text(
            "SELECT id, url, title, description, site_url, is_active, "
            "fetch_error_count, last_error, last_fetched_at, last_successful_at, "
            "etag, last_modified FROM rss_feeds"
        )).fetchall()
        for f in feeds:
            fid, url, title, desc, site_url, active, err_cnt, last_err, fetched_at, succ_at, etag, last_mod = f
            meta = json.dumps({"etag": etag, "last_modified": last_mod})
            existing = conn.execute(text(
                "SELECT id FROM sources WHERE kind='rss' AND external_id=:url"
            ), {"url": url}).fetchone()
            if not existing:
                conn.execute(text("""
                    INSERT INTO sources
                        (kind, external_id, url, title, description, site_url, is_active,
                         fetch_error_count, last_error, last_fetched_at, last_successful_at,
                         metadata_json, legacy_rss_feed_id)
                    VALUES ('rss', :url, :url, :title, :desc, :site_url, :active,
                            :err_cnt, :last_err, :fetched_at, :succ_at, :meta, :fid)
                """), {
                    "url": url, "title": title, "desc": desc, "site_url": site_url,
                    "active": active, "err_cnt": err_cnt, "last_err": last_err,
                    "fetched_at": fetched_at, "succ_at": succ_at, "meta": meta, "fid": fid,
                })
                rss_sources += 1

    # Backfill channel sources
    channel_sources = 0
    if "channels" in tables:
        chans = conn.execute(text(
            "SELECT id, username, title, description, is_active, "
            "fetch_error_count, last_error, last_fetched_at, channel_id, member_count "
            "FROM channels"
        )).fetchall()
        for c in chans:
            cid, uname, title, desc, active, err_cnt, last_err, fetched_at, chan_id, member_count = c
            url = f"https://t.me/{uname}" if uname else None
            meta = json.dumps({"channel_id": chan_id, "member_count": member_count})
            existing = conn.execute(text(
                "SELECT id FROM sources WHERE kind='telegram_channel' AND external_id=:uname"
            ), {"uname": uname}).fetchone()
            if not existing and uname:
                conn.execute(text("""
                    INSERT INTO sources
                        (kind, external_id, url, title, description, is_active,
                         fetch_error_count, last_error, last_fetched_at, metadata_json,
                         legacy_channel_id)
                    VALUES ('telegram_channel', :uname, :url, :title, :desc, :active,
                            :err_cnt, :last_err, :fetched_at, :meta, :cid)
                """), {
                    "uname": uname, "url": url, "title": title, "desc": desc,
                    "active": active, "err_cnt": err_cnt, "last_err": last_err,
                    "fetched_at": fetched_at, "meta": meta, "cid": cid,
                })
                channel_sources += 1

    logger.info(
        "signal_sources_migration rss_sources=%d channel_sources=%d",
        rss_sources, channel_sources,
    )


def downgrade() -> None:
    for table in ("user_signals", "topics", "feed_items", "subscriptions", "sources"):
        op.execute(text(f"DROP TABLE IF EXISTS {table}"))
