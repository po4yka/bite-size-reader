---
title: Port TopicSearchIndex to SQLAlchemy with TSVECTOR
status: backlog
area: db
priority: critical
owner: Nikita Pochaev
blocks:
  - migrate-postgres-baseline-alembic-revision
  - migrate-postgres-build-data-migrator
blocked_by:
  - migrate-postgres-port-models-core
created: 2026-05-06
updated: 2026-05-06
---

- [ ] #task Port TopicSearchIndex to SQLAlchemy with TSVECTOR #repo/ratatoskr #area/db #status/backlog 🔺

## Objective

Replace the SQLite FTS5 `TopicSearchIndex` model and the supporting
`TopicSearchIndexManager` with a SQLAlchemy 2.0 model backed by a `TSVECTOR`
generated column and a `GIN` index, while preserving the manager's public API.

## Context

Today (`app/db/_models_core.py:236-251` and `app/db/topic_search_index.py`):

- `FTS5Model` subclass with `SearchField` columns and `unicode61
  remove_diacritics 2` tokenizer.
- Lookups via raw SQL: `MATCH ?` + `bm25(...)`.
- Writes via raw SQL with FTS5-specific `'delete-all'` token.

Target (in `app/db/models/topic_search.py`):

```python
class TopicSearchIndex(Base):
    __tablename__ = "topic_search_index"

    request_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    url: Mapped[str | None] = mapped_column(String)
    title: Mapped[str | None] = mapped_column(String)
    snippet: Mapped[str | None] = mapped_column(String)
    source: Mapped[str | None] = mapped_column(String)
    published_at: Mapped[str | None] = mapped_column(String)
    body: Mapped[str | None] = mapped_column(String)
    tags: Mapped[str | None] = mapped_column(String)
    body_tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple', "
            "coalesce(title,'') || ' ' || coalesce(body,'') || ' ' || coalesce(tags,''))",
            persisted=True,
        ),
    )

    __table_args__ = (
        Index("ix_topic_search_body_tsv", "body_tsv", postgresql_using="gin"),
    )
```

Manager (`app/db/topic_search_manager.py`, replacing `topic_search_index.py`):

- `find_request_ids(topic, candidate_limit)` runs:
  ```sql
  SELECT request_id
  FROM topic_search_index
  WHERE body_tsv @@ websearch_to_tsquery('simple', :q)
  ORDER BY ts_rank_cd(body_tsv, websearch_to_tsquery('simple', :q)) DESC
  LIMIT :n;
  ```
  via `await session.execute(text(sql), {"q": topic, "n": candidate_limit})`.
- `refresh_index(request_id)` becomes a single `INSERT ... ON CONFLICT (request_id)
  DO UPDATE SET …` — Postgres updates `body_tsv` automatically because the
  generated column is recomputed on row write.
- `ensure_index()` becomes idempotent: schema is created by Alembic; this method
  rebuilds row content for any `Summary` whose payload changed since last seen.
- All FTS5 recovery code (`malformed` handling, drop+recreate) is deleted —
  Postgres GIN indexes do not corrupt under the operations we perform.

## Acceptance criteria

- [ ] `app/db/models/topic_search.py` defines `TopicSearchIndex` per the structure
      above; included in `ALL_MODELS`.
- [ ] `app/db/topic_search_manager.py` exposes the same public API as today's
      `TopicSearchIndexManager` (`ensure_index`, `refresh_index`,
      `find_request_ids`); callers in `app/application/services/topic_search_*` do
      not change.
- [ ] `websearch_to_tsquery('simple', …)` is used (matches the FTS5
      `unicode61 remove_diacritics 2` semantics most closely; safe handling of
      user input).
- [ ] Curated 10-query regression set in `tests/fixtures/topic_search_queries.json`
      (created in T3) returns ≥ 50% overlap with the SQLite result set on the
      same fixture data.
- [ ] No `MATCH` or `bm25` strings remain anywhere in the new code.
- [ ] Old `app/db/topic_search_index.py` is moved to
      `app/cli/_legacy_peewee_models/topic_search_index.py` (used by T2 read
      side), and its `TopicSearchIndexManager` class is renamed
      `LegacyTopicSearchIndexManager` to make confusion impossible.

## Notes

- Input worklist: `docs/explanation/peewee-sqlite-surface-audit.md`, especially
  the FTS5 section and topic-search raw SQL entries.
- Generated columns require Postgres ≥ 12. Pinning to 16 (T1) is more than safe.
- For per-row language switching (`'english'`/`'russian'`), file a follow-up; the
  `'simple'` tokenizer is correct for the migration.
