# CocoIndex Integration

CocoIndex is an opt-in, incremental ETL reconciler that keeps Qdrant in
sync with the Postgres `summaries` table. It runs inside the FastAPI
process as a background `FlowLiveUpdater` task.

## Quick start

```bash
# Install the extra
pip install -e ".[cocoindex]"

# Enable in .env
RATATOSKR_COCOINDEX_ENABLED=1
```

## How it works

Two paths write summary vectors to Qdrant:

| Path | Latency | Owner |
|------|---------|-------|
| **Fast path** (`SummaryEmbeddingGenerator`) | ~instant | write-through, best-effort |
| **CocoIndex flow** (`FlowLiveUpdater`) | ≤30s | authoritative, eventually-consistent |

Both paths produce the same Qdrant point UUID (`uuid5(NAMESPACE_OID, f"{request_id}:{summary_id}")`), so writes are idempotent. The fast path can silently lose a write; CocoIndex reconciles within one poll interval.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RATATOSKR_COCOINDEX_ENABLED` | `0` | Enable CocoIndex (set to `1` to activate) |
| `RATATOSKR_COCOINDEX_DSN` | *(DATABASE_URL)* | Override Postgres DSN for CocoIndex (strips asyncpg prefix automatically) |
| `RATATOSKR_COCOINDEX_POLL_INTERVAL_SEC` | `30` | Seconds between watermark polls when LISTEN/NOTIFY is idle |
| `RATATOSKR_COCOINDEX_LISTEN_CHANNEL` | `ratatoskr_summaries_changed` | Postgres LISTEN/NOTIFY channel |
| `RATATOSKR_COCOINDEX_BATCH_SIZE` | `32` | Rows per processing batch |
| `RATATOSKR_COCOINDEX_POOL_MAX` | `4` | Max psycopg3 connections |

## Connection budget

Ratatoskr uses three Postgres connection pools simultaneously when
CocoIndex and LangGraph checkpointing are both enabled:

| Pool | Driver | Connections |
|------|--------|-------------|
| SQLAlchemy (application) | asyncpg | `DB_POOL_SIZE` (default 5) |
| LangGraph checkpointer | psycopg3 | min=1, max=10 |
| CocoIndex flow | psycopg3 | max=4 + 1 (LISTEN/NOTIFY) |

Total worst-case: ~20 connections. Budget `max_connections` in Postgres
accordingly (default 100 is fine; set `RATATOSKR_COCOINDEX_POOL_MAX=2`
to reduce if needed).

## Startup failure isolation

CocoIndex startup errors are caught and logged (`cocoindex_startup_failed`)
without blocking FastAPI from serving requests. If CocoIndex fails to start,
the fast path continues as the sole writer to Qdrant.

## Rollback

1. Set `RATATOSKR_COCOINDEX_ENABLED=0` in `.env`
2. Redeploy — FastAPI starts without CocoIndex
3. Existing fast path + CLI backfill continue working unchanged

## CLI backfill with CocoIndex

```bash
# Use CocoIndex for a one-shot full-scan (instead of legacy backfill)
python -m app.cli.backfill_vector_store --use-cocoindex

# Legacy backfill (still works, default when --use-cocoindex is absent)
python -m app.cli.backfill_vector_store --limit=100 --dry-run
```

## v1 limitations

- **One point per summary** — CocoIndex v1 emits a single Qdrant point per
  summary, unlike the legacy backfill which emits chunked window points.
  This is a deliberate simplification; retrieval quality is measured before
  adding chunked points in a follow-up.
- **Alpha stability** — CocoIndex is pinned to `>=1.0.3,<1.1`. Pin review
  when 1.1 releases.
- **Trigger creation** — Requires the `ratatoskr` Postgres role to have
  `TRIGGER` privilege on `summaries`. Migration 0007 grants this; verify
  the role name matches your deployment.

## CocoIndex bookkeeping schema

CocoIndex stores its watermark and metadata tables in a dedicated `cocoindex`
Postgres schema (created by migration 0007). These tables are managed
entirely by CocoIndex and should not be modified manually.
