---
title: Port feature models to SQLAlchemy 2.0
status: review
area: db
priority: critical
owner: Nikita Pochaev
blocks:
  - migrate-postgres-baseline-alembic-revision
  - migrate-postgres-port-persistence-repositories
  - migrate-postgres-build-data-migrator
created: 2026-05-06
updated: 2026-05-06
---

- [ ] #task Port feature models to SQLAlchemy 2.0 #repo/ratatoskr #area/db #status/review 🔺

## Objective

Port the remaining ~38 Peewee models (digest, RSS, rules, signal, batch,
collections, aggregation, user-content) to SQLAlchemy 2.0 typed declarative.

## Context

In-scope source files and target output (one target file per source file):

| Source | Target |
|--------|--------|
| `app/db/_models_aggregation.py` | `app/db/models/aggregation.py` |
| `app/db/_models_batch.py`       | `app/db/models/batch.py` |
| `app/db/_models_collections.py` | `app/db/models/collections.py` |
| `app/db/_models_digest.py`      | `app/db/models/digest.py` |
| `app/db/_models_rss.py`         | `app/db/models/rss.py` |
| `app/db/_models_rules.py`       | `app/db/models/rules.py` |
| `app/db/_models_signal.py`      | `app/db/models/signal.py` |
| `app/db/_models_user_content.py`| `app/db/models/user_content.py` |

Conventions: identical to M1.

When M2 is complete, the legacy `app/db/_models_*.py` files are moved verbatim into
`app/cli/_legacy_peewee_models/` (see M1 notes) so the data migrator (T2) keeps a
working Peewee read-side. None of the new application code imports from the legacy
package.

## Acceptance criteria

- [x] All eight target files exist; every Peewee model class in scope has a
      SQLAlchemy 2.0 equivalent.
- [x] FK relationships from feature models back into core models
      (e.g. `ChannelSubscription.user → User`,
      `SummaryFeedback.summary → Summary`) are declared with `relationship(...,
      back_populates=...)` on both sides.
- [x] `JSONB` columns with `default=list` / `default=dict` (e.g. `events_json`,
      `conditions_json`) preserve those defaults via callable defaults in
      `mapped_column(JSONB, default=list)`.
- [x] `ALL_MODELS` tuple in `app/db/models/__init__.py` extends to include every
      M2 class; ordering preserves topological FK dependency for the migrator.
- [x] `app/db/_models_*.py` files moved into `app/cli/_legacy_peewee_models/`
      (one file each) and re-exported from a single `__init__.py` so T2 can
      import them as one symbol set. Application code no longer imports them.
- [x] Per-model fixture tests pass against an ephemeral Postgres (extends
      `tests/db/test_models_*.py` started in M1).
- [x] `mypy` clean.

## Notes

- Input worklist: `docs/explanation/peewee-sqlite-surface-audit.md`, especially
  the Model Fields section entries for all feature `_models_*.py` files.
- Watch for circular imports between `core.py` and the feature modules — declare
  relationships with string targets (`relationship("Summary", …)`) and resolve
  via SQLAlchemy's lazy registry.
- `app/db/_models_signal.py` defines the most recently added models
  (`Source`, `Subscription`, `FeedItem`, `Topic`, `UserSignal`); double-check
  their indexes.

Progress:

- Added all eight feature SQLAlchemy model modules and extended `ALL_MODELS` to
  52 SQLAlchemy classes.
- Restored the frozen Peewee snapshot under `app/cli/_legacy_peewee_models/` from
  git history for the T2 read-side migrator.
- `tests/db/test_models_core.py tests/db/test_models_features.py` passed against a
  throwaway Postgres 16 container on 2026-05-06.
