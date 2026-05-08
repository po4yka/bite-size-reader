# Ratatoskr — Technical Specification

> This page is a navigation index. All substantive content lives in the linked canonical pages.

Async Telegram bot: accepts web article URLs, YouTube videos, and forwarded channel posts; summarizes via a multi-provider scraper chain and OpenRouter LLM; persists relational artifacts in PostgreSQL. Also exposes a FastAPI mobile API, a React web frontend, and an MCP server for external AI agents.

---

## Architecture

Component diagram, request lifecycle, layered (hexagonal) view, goals, non-goals, user/access-control model, and the canonical subsystem index.

→ [Architecture Overview](explanation/architecture-overview.md)

---

## Data Model

Complete PostgreSQL schema reference: all core tables (users, requests, crawl_results, llm_calls, summaries, aggregation sessions, signal-scoring tables), indexes, relationships, ER diagram, common queries, database maintenance, migrations, mixed-source aggregation model, and URL normalization/deduplication rules.

→ [Data Model Reference](reference/data-model.md)

Telethon session files are the only intentional SQLite carve-out. They are
client session stores owned by Telethon, validated by
`app/adapters/digest/session_validator.py`, and are not part of Ratatoskr's
relational store or PostgreSQL migration.

---

## Summary JSON Contract

Strict JSON schema enforced on every summary: field definitions, character limits, array lengths, enums, validation rules, self-correction loop, backward-compatibility policy, and a complete example.

→ [Summary Contract Reference](reference/summary-contract.md) · [Contract Design](explanation/summary-contract-design.md)

---

## Mobile REST API

Full endpoint index, envelope/error contract, authentication modes (Telegram login, secret-key flow, JWT refresh), aggregations surface, signal scoring surface, sync model, search parameters, collections, digest, and system-maintenance endpoints.

→ [Mobile API Reference](reference/mobile-api.md)

Machine-readable contract: `docs/openapi/mobile_api.yaml` / `docs/openapi/mobile_api.json`

---

## API Contracts and Error Codes

External service API shapes (Firecrawl, OpenRouter, Telethon, yt-dlp) with request/response examples, rate limits, and error handling; plus the full internal error-code catalog (AUTH, VAL, EXT, LLM, YT, DB, SYNC, RATE, SYS, REDIS, VECTOR families).

→ [External API Contracts](reference/api-contracts.md) · [Error Codes Reference](reference/api-error-codes.md)

---

## Scraper Chain

Eight-provider ordered fallback chain (Scrapling → Crawl4AI → Firecrawl self-hosted → Defuddle → Playwright → Crawlee → direct HTML → ScrapeGraphAI): provider taxonomy, deployment topology, quality gates, anti-fingerprinting, and configuration recipes.

→ [Scraper Chain Explanation](explanation/scraper-chain.md)

---

## Multi-Agent Architecture

Four specialized agents (ContentExtraction, Summarization, Validation, WebSearch) coordinated by AgentOrchestrator; self-correction feedback loop; signal-scoring v0 integration; usage examples and test hints.

→ [Multi-Agent Architecture](explanation/multi-agent-architecture.md)

---

## Environment Variables and Configuration

Complete reference for all environment variables grouped by subsystem, plus YAML config file reference.

→ [Environment Variables Reference](reference/environment-variables.md) · [YAML Config Reference](reference/config-file.md)

---

## Deployment and Operations

Production deployment guide, Docker Compose profiles, volume mounts, and channel-digest subsystem ops.

→ [Production Deployment Guide](guides/deploy-production.md) · [Digest Subsystem Ops](reference/digest-subsystem-ops.md) · [Pi SQLite→Postgres Cutover Runbook](runbooks/pi-postgres-cutover.md)

---

## Troubleshooting and FAQ

Common failure modes, debugging workflow, external API error resolution, and frequently asked questions.

→ [Troubleshooting Reference](reference/troubleshooting.md) · [FAQ](explanation/faq.md)

---

## Web Frontend

React SPA serving contract, routes, hybrid auth modes, and local development workflow.

→ [Web Frontend Reference](reference/frontend-web.md)

---

## Observability

Prometheus metrics, structured logs, correlation-ID tracing, and the Loki/Promtail/Grafana monitoring stack.

→ [Observability Strategy](explanation/observability-strategy.md)

---

## GitHub Repository Schema

Three tables added by the GitHub repository ingestion subsystem
(`app/db/models/repository.py`). They have no foreign key to `summaries`;
repos use the `RepoAnalysis` contract, not the 35-field `Summary` contract.

### `repositories`

| Column | Type | Null | Purpose |
|--------|------|------|---------|
| `id` | integer PK | no | Auto-increment surrogate key |
| `github_id` | bigint | no | GitHub's stable numeric repo ID |
| `owner` | varchar(100) | no | Owner login |
| `name` | varchar(200) | no | Repo name |
| `full_name` | varchar(320) | no | `owner/name` |
| `url` | varchar(500) | no | Canonical `https://github.com/owner/repo` URL |
| `homepage_url` | varchar(500) | yes | Project homepage |
| `description` | text | yes | GitHub description |
| `primary_language` | varchar(100) | yes | Dominant language |
| `languages_json` | jsonb | yes | Full language breakdown: `{"Python": 12345}` |
| `topics_json` | jsonb | yes | Topic list: `["web", "async"]` |
| `stars` | integer | no | Star count; refreshed every sync |
| `forks` | integer | no | Fork count; refreshed every sync |
| `watchers` | integer | no | Watcher count; refreshed every sync |
| `default_branch` | varchar(100) | yes | Default branch for README fetch |
| `license_spdx` | varchar(100) | yes | SPDX license identifier |
| `is_archived` | boolean | no | Archived on GitHub |
| `is_fork` | boolean | no | Fork of another repo |
| `is_template` | boolean | no | Template repo |
| `pushed_at` | timestamptz | yes | Last push time |
| `created_at_github` | timestamptz | yes | Repo creation time on GitHub |
| `readme_excerpt` | text | yes | First `GITHUB_README_MAX_BYTES` of raw README |
| `readme_etag` | varchar(200) | yes | HTTP ETag; reserved for conditional fetch |
| `analysis_json` | jsonb | yes | LLM-derived `RepoAnalysis` fields |
| `analysis_model` | varchar(200) | yes | Model used; surfaced for re-analyze affordance |
| `analysis_at` | timestamptz | yes | When analysis was last computed |
| `content_hash` | varchar(64) | yes | SHA256 of `description + sorted(topics) + readme_excerpt` |
| `source` | repo_source enum | no | `manual` or `starred` |
| `is_starred` | boolean | no | Currently in user's GitHub stars |
| `user_id` | bigint FK | no | References `users.telegram_user_id` |
| `last_synced_at` | timestamptz | no | Last metadata pull from GitHub |
| `pending_analysis` | boolean | no | LLM analysis deferred by budget cap |
| `created_at` | timestamptz | no | Row insertion time |
| `updated_at` | timestamptz | no | Last modification time |

Unique constraint: `(user_id, github_id)`.
Indexes: `(user_id, is_starred)`, `(user_id, primary_language)`, `(user_id, pushed_at DESC)`, `(github_id)`.

### `repository_embeddings`

| Column | Type | Null | Purpose |
|--------|------|------|---------|
| `id` | integer PK | no | Surrogate key |
| `repository_id` | integer FK unique | no | References `repositories.id` ON DELETE CASCADE |
| `model_name` | varchar(200) | no | Embedding model identifier |
| `model_version` | varchar(50) | no | Version; backfill CLI detects staleness on mismatch |
| `embedding_blob` | bytea | no | Serialized float32 embedding |
| `dimensions` | integer | no | Vector dimensionality |
| `language` | varchar(10) | yes | Language of embedded text |
| `created_at` | timestamptz | no | Row insertion time |

### `user_github_integrations`

| Column | Type | Null | Purpose |
|--------|------|------|---------|
| `id` | integer PK | no | Surrogate key |
| `user_id` | bigint FK unique | no | References `users.telegram_user_id` ON DELETE CASCADE |
| `auth_method` | github_auth_method enum | no | `pat` or `oauth_device` |
| `encrypted_token` | bytea | no | Fernet-encrypted access token |
| `token_scopes` | varchar(500) | yes | Scopes from GitHub token validation |
| `github_login` | varchar(100) | yes | Cached GitHub username |
| `github_user_id` | bigint | yes | GitHub's numeric user ID |
| `status` | github_integration_status enum | no | `active`, `needs_reauth`, or `revoked` |
| `last_synced_at` | timestamptz | yes | Most recent sync completion time |
| `last_sync_cursor` | varchar(500) | yes | Reserved for pagination cursor |
| `last_full_sync_at` | timestamptz | yes | Most recent full-pagination sync completion |
| `notified_needs_reauth_at` | timestamptz | yes | When the one-shot reauth DM was sent |
| `created_at` | timestamptz | no | Row insertion time |
| `updated_at` | timestamptz | no | Last modification time |

→ [GitHub Repository Ingestion](explanation/github-repository-ingestion.md) for data-flow, sync algorithm, and cost model.

---

*Last updated: 2026-05-08*
