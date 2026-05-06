---
title: Port core models to SQLAlchemy 2.0
status: backlog
area: db
priority: critical
owner: Nikita Pochaev
blocks:
  - migrate-postgres-port-models-features
  - migrate-postgres-port-topic-search-model
  - migrate-postgres-port-runtime-services
  - migrate-postgres-baseline-alembic-revision
blocked_by:
  - migrate-postgres-introduce-database-factory
  - migrate-postgres-audit-sqlite-surface
created: 2026-05-06
updated: 2026-05-06
---

- [ ] #task Port core models to SQLAlchemy 2.0 #repo/ratatoskr #area/db #status/backlog 🔺

## Objective

Define the SQLAlchemy 2.0 declarative `Base` and port the eleven core models that
the bot's hot path depends on, so the rest of the migration has a stable target.

## Context

Core scope (matches `app/db/_models_core.py`):

- `User`, `ClientSecret`, `Chat`
- `Request`, `TelegramMessage`, `CrawlResult`, `LLMCall`, `Summary`
- `UserInteraction`, `AuditLog`, `SummaryEmbedding`
- `VideoDownload`, `AudioGeneration`, `AttachmentProcessing`
- `UserDevice`, `RefreshToken`

(`TopicSearchIndex` is **not** here — it has its own task M3.)

Target structure:

```
app/db/
├── base.py            # class Base(DeclarativeBase): ...
├── types.py           # JSONB shim, TSVECTOR re-export, _utcnow column default
└── models/
    ├── __init__.py    # re-exports all classes; ALL_MODELS tuple
    ├── core.py        # User, Chat, Request, TelegramMessage, CrawlResult,
    │                  # LLMCall, Summary, UserInteraction, AuditLog, ...
    └── … (M2)
```

Conventions:

- All models use `Mapped[T]` + `mapped_column(...)` typed style.
- Timestamps are `DateTime(timezone=True)` and default to a `_utcnow()` callable
  (preserve TZ-awareness present in the current `_utcnow` helper).
- Server-version columns become `BigInteger` with a `default=_next_server_version`;
  the `BaseModel.save()` monotonic-version logic in
  `app/db/_models_base.py:29-45` moves into a SQLAlchemy `before_update` event
  handler registered against `Base`.
- JSON columns use `Mapped[dict | list | None] = mapped_column(JSONB)`.
- All FKs use `ondelete=` matching today's `on_delete=` semantics
  (e.g. `User.devices` cascade, `Request.summary` cascade).
- Indexes declared via `__table_args__ = (Index(...), ...)`.

## Acceptance criteria

- [ ] `app/db/base.py`, `app/db/types.py`, `app/db/models/__init__.py`,
      `app/db/models/core.py` exist with the eleven core classes ported.
- [ ] Field types, defaults, nullability, indexes, and FKs are 1:1 with
      `_models_core.py` plus the equivalents in `_models_base.py` (timestamp
      defaults, server-version monotonic update via event listener).
- [ ] `mypy` clean across the new files.
- [ ] A unit test fixture (`tests/db/test_models_core.py`) instantiates each
      model, persists via `AsyncSession`, reads back, asserts equality on every
      field. Runs against an ephemeral Postgres in CI.
- [ ] No reference to `peewee`, `playhouse`, `database_proxy`, or `BaseModel`
      remains in any file under `app/db/models/core.py`.
- [ ] `ALL_MODELS` tuple in `app/db/models/__init__.py` re-exports the M1
      classes; M2 will extend it.
- [ ] The legacy file `app/db/_models_core.py` is **kept** for now (used by the
      legacy migrator snapshot in T2). It is moved verbatim to
      `app/cli/_legacy_peewee_models/_core.py` only when M2 lands.

## Notes

- Input worklist: `docs/explanation/peewee-sqlite-surface-audit.md`, especially
  the Model Fields section entries for `_models_base.py` and `_models_core.py`.
- The monotonic `server_version` logic must be unit-tested explicitly — it's the
  one piece of business logic in the old `BaseModel`, not just metadata.
- For `User.preferences_json` (and similar JSONB columns) declare
  `mapped_column(JSONB, nullable=True)` not just `JSONB` — the implicit nullable
  default differs from Peewee's.
