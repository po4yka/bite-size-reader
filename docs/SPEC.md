# Ratatoskr — Technical Specification

> This page is a navigation index. All substantive content lives in the linked canonical pages.

Async Telegram bot: accepts web article URLs, YouTube videos, and forwarded channel posts; summarizes via a multi-provider scraper chain and OpenRouter LLM; persists all artifacts in SQLite. Also exposes a FastAPI mobile API, a React web frontend, and an MCP server for external AI agents.

---

## Architecture

Component diagram, request lifecycle, layered (hexagonal) view, goals, non-goals, user/access-control model, and the canonical subsystem index.

→ [Architecture Overview](explanation/architecture-overview.md)

---

## Data Model

Complete SQLite schema reference: all core tables (users, requests, crawl_results, llm_calls, summaries, aggregation sessions, signal-scoring tables), indexes, relationships, ER diagram, common queries, database maintenance, migrations, mixed-source aggregation model, and URL normalization/deduplication rules.

→ [Data Model Reference](reference/data-model.md)

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

External service API shapes (Firecrawl, OpenRouter, Telethon, yt-dlp) with request/response examples, rate limits, and error handling; plus the full internal error-code catalog (AUTH, VAL, EXT, LLM, YT, DB, SYNC, RATE, SYS, REDIS, CHROMA families).

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

→ [Production Deployment Guide](guides/deploy-production.md) · [Digest Subsystem Ops](reference/digest-subsystem-ops.md)

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

*Last updated: 2026-05-05*
