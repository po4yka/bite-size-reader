# Tech Design: Redis Caching for Firecrawl and LLM
- Doc ID: TD-redis-cache
- Date: 2025-12-07
- Owner: AI Dev Partner
- Status: Draft
- Related Docs: OVERVIEW-01_project_goals.md, ARC-01_overall_architecture.md, TS-redis-cache.md

## Summary
Add a Redis-backed request-level cache to reduce Firecrawl/API calls and LLM cost/latency. Keys combine normalized URL hash and route/prompt version to avoid collisions. Cache is optional (feature-flagged) and fails open.

## Goals / Non-Goals
- Goals: Lower latency and cost; dedupe identical requests; reuse stable summaries for identical prompt/version.
- Non-goals: Cross-user auth caching, long-term persistence, cache invalidation via admin UI.

## Context & Constraints
- Single-instance bot with async flows; semaphore limits external calls.
- Redis assumed reachable at 127.0.0.1:6379 DB0 by default; configurable via env.
- Keep cache read/write lightweight and non-blocking; never block critical path on cache failures.

## Architecture
- New module `app/infrastructure/cache/redis_cache.py` providing async get/set JSON with namespaced keys and TTL.
- Config: `runtime.cache.enabled`, host, port, db, prefix, Firecrawl TTL (6h), LLM TTL (2h).
- Feature flag to disable cache globally.

## Key Schema
- Firecrawl: `bsr:fc:{route_version}:{hash}` where `hash=url_hash_sha256(normalized_url)`.
- LLM summary: `bsr:llm:{prompt_version}:{model}:{lang}:{hash}`; hash derived from request normalized URL hash (or explicit hash if available).
- Values: JSON payloads storing serialized FirecrawlResult-like dict and shaped summary dict. Include checksum/version to detect incompatible formats.

## Flows
- Firecrawl: Before scrape, try cache → if hit, reuse content (respect low-value rules). After successful scrape or salvage, write cache with TTL. Do not cache low-value or error results. TTL should not exceed the Firecrawl v2 `maxAge` used on the request (default 2 days; current Redis TTL 6h is safely below).
- LLM: Before OpenRouter call, try cache → if hit, return shaped summary and skip call. After successful summary, write cache. Do not cache invalid/empty summaries or errors.

## Failure, Reliability, Performance
- Fail open: any Redis error logs a warning and proceeds without cache.
- Timeouts: short (e.g., 200-300 ms) per op to avoid blocking.
- Avoid caching poison responses: skip cache on status != ok, empty content, failed validation.

## Security & Privacy
- No secrets in cache values. Keys contain only hashes/prompt versions. Respect access control upstream.

## Observability
- Structured logs for cache hits/misses/set/errors with correlation_id and request_id where available.
- Metrics hooks (future) via logger fields.

## Testing Strategy
- See TS-redis-cache.md: unit tests for helper; integration tests for extractor/summarizer cache hit/miss/ttl/feature-flag/error cases.

## Rollout / Migration
- Backward compatible: default enabled with safe defaults; can disable via env.
- No DB migrations.

## Risks & Mitigations
- Stale data: use moderate TTLs and key versioning; bump prompt/version on contract changes.
- Cache stampede: semaphore already limits; cache writes after first success reduce repeat calls.
- Redis unavailable: fail open and log.

## Open Questions
- Should we expose admin flush command? (out of scope for now)
