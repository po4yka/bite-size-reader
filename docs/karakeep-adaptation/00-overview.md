# Karakeep Feature Adaptation -- Overview

This document maps Karakeep's product features against Bite-Size Reader (BSR), identifies gaps, defines adaptation principles, and scopes the work.

## What is Karakeep?

[Karakeep](https://github.com/karakeep-app/karakeep) is a self-hosted bookmarking platform (Node.js / Next.js / tRPC / Drizzle ORM) with web, mobile, browser extension, CLI, and MCP interfaces. It crawls saved URLs, extracts metadata, takes screenshots, runs AI tagging/summarization, and indexes content for full-text search.

## Feature Mapping

| Karakeep Feature | BSR Status | Notes |
|---|---|---|
| Bookmark CRUD (links, text, assets) | Complete | BSR calls these "summaries" + "requests" |
| Web crawling pipeline | Complete | Multi-provider scraper chain with fallbacks |
| AI auto-tagging | Partial | LLM generates `topic_tags` in summary JSON, but no user-editable tag system |
| AI summarization | Complete | Core BSR capability -- multi-agent with self-correction |
| Manual user tags | **Missing** | See [01-user-tags.md](01-user-tags.md) |
| Lists / collections | Complete | BSR has nested collections with collaborators and invites |
| Favorites | Complete | `is_favorited` on Summary model |
| Archive | Complete | Soft delete with `is_deleted` / `deleted_at` |
| Full-text search | Complete | FTS5 + ChromaDB semantic + hybrid search |
| Reader view | Complete | Carbon web article view with markdown rendering |
| Highlights / annotations | Complete | `SummaryHighlight` model with colors and notes |
| Reading progress | Complete | `reading_progress` float + `last_read_offset` on Summary |
| RSS feed subscriptions | Complete (different) | BSR has Telegram channel digests instead of RSS. Equivalent purpose. |
| Rule engine (automation) | **Missing** | See [02-rule-engine.md](02-rule-engine.md) |
| Per-user webhooks | **Partial** | System-wide webhook only. See [03-per-user-webhooks.md](03-per-user-webhooks.md) |
| Bulk import/export | **Missing** | Only per-summary PDF export exists. See [04-bulk-import-export.md](04-bulk-import-export.md) |
| Browser extension | **Missing** | See [05-browser-extension.md](05-browser-extension.md) |
| Enhanced admin panel | **Partial** | Basic DB stats only. See [06-admin-panel.md](06-admin-panel.md) |
| User-level backups | **Partial** | System-level SQLite backup only. See [07-user-backups.md](07-user-backups.md) |
| Multi-device sync | Complete | Full/delta sync with OCC via `server_version` |
| MCP server | Complete | BSR has 17 tools + 13 resources (richer than Karakeep's 7 tools) |
| CLI tool | Partial | BSR has `app/cli/` tools but not a standalone distributable CLI |
| SDK (TypeScript) | N/A | BSR is Python-first; OpenAPI spec exists for client generation |
| Mobile app (Expo) | Out of scope | BSR uses web frontend + Telegram as mobile interface |
| Stripe billing | Out of scope | BSR is a personal/small-team tool |
| Statistics / analytics | Complete | Reading stats, goals, streaks, activity tracking |
| User preferences | Complete | `preferences_json` on User model + API |
| Karakeep sync | Complete | Bidirectional sync adapter already exists (`app/adapters/karakeep/`) |

## Gap Summary

| # | Feature | Spec | Complexity | Depends On |
|---|---------|------|------------|------------|
| 1 | User Tagging System | [01-user-tags.md](01-user-tags.md) | Medium | -- |
| 2 | Rule Engine | [02-rule-engine.md](02-rule-engine.md) | Large | Tags, Webhooks, EventBus |
| 3 | Per-User Webhooks | [03-per-user-webhooks.md](03-per-user-webhooks.md) | Small | EventBus |
| 4 | Bulk Import/Export | [04-bulk-import-export.md](04-bulk-import-export.md) | Medium | Tags |
| 5 | Browser Extension | [05-browser-extension.md](05-browser-extension.md) | Medium | Quick-save API, Tags |
| 6 | Enhanced Admin Panel | [06-admin-panel.md](06-admin-panel.md) | Medium | -- |
| 7 | User-Level Backups | [07-user-backups.md](07-user-backups.md) | Small | -- |

Build order and phasing: [08-phasing-and-priorities.md](08-phasing-and-priorities.md)

## Adaptation Principles

### 1. Summarization-first, not bookmarking-first

Karakeep is a bookmark manager with optional AI. BSR is an AI summarization tool with optional organization. Every adapted feature must serve the reading/summarization workflow. Do not add features that only make sense for raw bookmark storage.

### 2. Telegram-first UX

Every feature should have a Telegram bot interaction path, not just API/web. The Telegram bot is the primary interface for most BSR users. Browser extension and web UI are secondary entry points.

### 3. SQLite single-file simplicity

Do not introduce new infrastructure services (Redis, Meilisearch, Postgres). BSR's strength is single-file SQLite deployment. New features must work with SQLite. Optional dependencies (ChromaDB, Redis) remain optional.

### 4. Hexagonal architecture compliance

All new features go through the domain layer (`app/domain/`), not directly from API routers to database models. Follow the existing ports-and-adapters pattern:

- Domain models in `app/domain/`
- Application services / use cases in `app/application/`
- Infrastructure (persistence, messaging) in `app/infrastructure/`
- API routers in `app/api/routers/`
- Telegram handlers in `app/adapters/telegram/`

### 5. Incremental, not big-bang

Each feature spec is independent and deployable on its own. No feature requires all others to be built first. Dependencies are documented in the phasing guide.

## Out of Scope

These Karakeep features will NOT be adapted:

- **Mobile app (Expo/React Native)** -- BSR's web frontend + Telegram bot covers mobile use cases. A native app is a separate strategic decision.
- **Stripe billing / subscription tiers** -- BSR is a personal/small-team tool. No multi-tenant billing needed.
- **Collaboration beyond collections** -- BSR already has collection collaborators with invite tokens. No additional sharing mechanisms needed.
- **Meilisearch integration** -- BSR uses FTS5 + ChromaDB. No need for another search engine.
- **OpenAPI SDK generation** -- BSR already has OpenAPI specs. Client generation is a build step, not a feature.

## Reference Architecture

```
Telegram Bot  <-->  FastAPI API  <-->  Web Frontend (Carbon)
      |                 |                     |
      +--------+--------+---------------------+
               |
        Domain Layer (app/domain/)
               |
     Application Layer (app/application/)
               |
   +-----+-----+-----+-----+
   |     |     |     |     |
  DB   Event  Cache Search Webhook
       Bus
```

New features plug into this architecture at the domain and application layers, with presentation bindings in Telegram, API, and web.
