# Test Plan: Redis Caching for Firecrawl and LLM
- Doc ID: TS-redis-cache
- Date: 2025-12-07
- Owner: AI Dev Partner
- Status: Draft
- Related Docs: TD-redis-cache.md

## Scope
- Verify Redis-based caching for Firecrawl results and LLM summaries.
- Ensure cache is optional, safe, and does not regress existing flows.

## In-Scope
- Cache helper get/set behavior, TTL, serialization.
- Firecrawl path: hit/miss, skip on low-value/error, salvage caching, feature flag off.
- LLM path: hit/miss, skip on invalid/empty, prompt/model/lang keying, feature flag off.

## Out-of-Scope
- Redis clustering/HA.
- Admin cache eviction tooling.

## Environments
- Local with Redis at 127.0.0.1:6379 DB0 (configurable via env).

## Test Matrix
- Unit: redis_cache helper (keys, namespaces, TTL, fail-open on errors).
- Integration: content_extractor uses cached crawl; llm_summarizer uses cached summary; salvage caching; feature flag disabled; TTL expiry mocked.
- Regression: ensure persistence still occurs; no caching of low-value or error results.

## Test Cases (examples)
- Cache hit returns stored crawl/summary and skips external call.
- Cache miss triggers external call then stores entry with correct TTL.
- Cache disabled -> no Redis calls.
- Redis error -> warning logged, flow continues.
- Low-value Firecrawl result -> not cached.
- LLM invalid/empty summary -> not cached.
- Prompt version/model/lang change -> cache miss.
- TTL expiry simulated -> miss after expiry.

## Data & Fixtures
- Fake Redis client or embedded server; serialized FirecrawlResult/summary payloads.
- Sample normalized URL hashes and prompt versions.

## Entry / Exit Criteria
- Entry: code merged with feature flag and config defaults.
- Exit: tests added/updated, passing locally (unit/integration relevant set).

## Reporting
- Use pytest output; track cache hit/miss assertions.

## Open Questions
- Need dedicated CI Redis service? (fallback to mock if unavailable)
