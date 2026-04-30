# ADR-0006: Multi-Provider Content Extraction with Fallback Chain

**Date:** 2026-03-06

**Status:** Accepted

**Deciders:** po4yka

**Technical Story:** Reduce single-point-of-failure dependency on cloud Firecrawl API

## Context

ADR-0001 chose the Firecrawl cloud API as the sole content extractor. While Firecrawl provides excellent extraction quality, relying on a single cloud API creates several problems:

1. **Single Point of Failure**: If the Firecrawl cloud API goes down, all content extraction stops
2. **Ongoing API Costs**: Every scrape consumes a paid API credit ($25/month for 5,000 credits)
3. **External Latency**: Each request adds 2-5s of round-trip latency to a third-party service
4. **No Offline Mode**: The bot cannot function without internet access and a valid API key

Since ADR-0001, the landscape has changed:

- **Scrapling** now provides high-quality in-process content extraction with TLS impersonation, handling many anti-bot protections without an external API
- **Firecrawl can be self-hosted** via Docker Compose, eliminating cloud API dependency while retaining its extraction capabilities
- The project already had a `_attempt_direct_html_salvage()` method that duplicated fallback logic in an ad-hoc manner, indicating a need for a structured fallback strategy

## Decision

We will introduce a `ContentScraperChain` with ordered fallback providers:

1. **Scrapling** (primary) -- in-process extraction, zero cost, no external dependency
2. **Self-hosted Firecrawl** (secondary) -- runs in the same Docker Compose stack
3. **Playwright browser rendering** (tertiary) -- JavaScript-heavy fallback before direct fetch
4. **Crawlee hybrid extraction** (quaternary) -- `BeautifulSoupCrawler` followed by `PlaywrightCrawler` for difficult pages
5. **Direct HTML fetch** via httpx + trafilatura (last resort) -- lightweight final fallback

The chain follows the existing `LLMClientProtocol` pattern (Protocol + Factory + Providers). The `ContentScraperChain` implements the scraper protocol itself (composite pattern), making it a drop-in replacement for any single provider.

Key design decisions:

- **Keep `FirecrawlResult` as the universal output model.** It is referenced in 16+ files across the codebase. All providers normalize their output into this model, avoiding a disruptive refactor.
- **Make `FIRECRAWL_API_KEY` optional.** It is only required when using the cloud Firecrawl provider or the web search API. The bot can now run with zero external API keys for basic content extraction.
- **Preserve cloud Firecrawl for TopicSearchService.** The search API has no in-process alternative, so `TopicSearchService` still calls cloud Firecrawl directly.
- **Remove `_attempt_direct_html_salvage()`.** This ad-hoc fallback is now handled by `DirectHTMLProvider`, eliminating duplicate logic.

## Consequences

### Positive

- No external dependency for basic content extraction (Scrapling works offline)
- Cost reduction (Scrapling is free; self-hosted Firecrawl has no per-request cost)
- Improved resilience via automatic fallback chain -- if one provider fails, the next is tried
- Cleaner code (removed duplicate salvage logic from the content extractor)

### Negative

- More complex configuration (7 new environment variables for provider selection and tuning)
- Scrapling may have lower extraction quality than Firecrawl for JavaScript-heavy sites
- Self-hosted Firecrawl adds Docker resource usage (~1GB RAM)

### Neutral

- Cloud Firecrawl remains available as a provider option and can be added to the chain
- TopicSearchService (web search enrichment) still requires a cloud Firecrawl API key

## Alternatives Considered

### Alternative 1: Replace Firecrawl with Scrapling entirely

Remove Firecrawl completely and use only Scrapling for all content extraction.

**Pros:**

- Simplest configuration (single provider)
- Zero API costs

**Cons:**

- No JavaScript rendering (fails on React/Vue/Angular apps)
- Lower extraction quality on complex sites
- No fallback if Scrapling fails

**Why not chosen:** Too aggressive. Firecrawl still provides superior quality for JS-heavy sites. A fallback chain gives the best of both worlds.

### Alternative 2: Keep cloud Firecrawl as primary, add Scrapling as fallback only

Maintain the existing architecture but add Scrapling as a fallback for Firecrawl failures.

**Pros:**

- Minimal change from current architecture
- Highest extraction quality as default

**Cons:**

- Still incurs per-request API costs for every successful extraction
- Still depends on external service availability for the primary path
- Does not address latency concern

**Why not chosen:** Does not address cost or latency goals. The chain approach allows users to choose their preferred ordering based on their priorities.

## Decision Criteria

- **Resilience** (High): Must not have a single point of failure for content extraction
- **Cost** (High): Should reduce or eliminate per-request API costs
- **Extraction Quality** (High): Must maintain high-quality extraction for most sites
- **Code Simplicity** (Medium): Should follow existing patterns and reduce duplication
- **Configuration Flexibility** (Medium): Users should be able to customize the provider chain
- **Latency** (Low): In-process extraction is a bonus, not a hard requirement

## Related Decisions

- [ADR-0001](0001-use-firecrawl-for-content-extraction.md) - Extended by this ADR; Firecrawl remains an option but is no longer the sole provider
- [ADR-0004](0004-hexagonal-architecture.md) - The Protocol + Factory + Provider pattern follows the hexagonal architecture established here

## Implementation Notes

- **Protocol**: `app/adapters/content/scraper/protocol.py`
- **Chain**: `app/adapters/content/scraper/chain.py`
- **Factory**: `app/adapters/content/scraper/factory.py`
- **Providers**: `scrapling_provider.py`, `firecrawl_provider.py`, `playwright_provider.py`, `crawlee_provider.py`, `direct_html_provider.py`
- **Config**: `app/config/scraper.py` (`ScraperConfig`)
- **Config v2**: `SCRAPER_*` controls now include profile tuning (`SCRAPER_PROFILE`), global/brower switches, force-provider override, and explicit direct-html/firecrawl-self-hosted tuning knobs. Legacy `SCRAPLING_*` and `SCRAPER_DIRECT_HTTP_ENABLED` names are fail-fast deprecated.
- **Docker**: The current `ops/docker/docker-compose.yml` can point at an externally managed self-hosted Firecrawl API via `firecrawl-api:host-gateway`; it does not yet define a Firecrawl service. A dedicated Compose profile is planned in the refactoring roadmap.
- **Tests**: `tests/test_scraper_chain.py` (45 tests)

## Notes

**2026-03-06**: This ADR extends but does not supersede ADR-0001. Cloud Firecrawl remains a valid provider option, and the web search API still requires a cloud Firecrawl API key.
**2026-03-06**: Playwright browser fallback was added between Firecrawl and direct HTML for JS-heavy pages.
**2026-03-06**: Crawlee hybrid fallback was added before direct HTML as an advanced single-page extractor.

---

### Update Log

| Date | Author | Change |
| ------ | -------- | -------- |
| 2026-03-06 | po4yka | Initial decision (Accepted) |
| 2026-03-06 | po4yka | Added Playwright fallback tier before direct HTML |
| 2026-03-06 | po4yka | Added Crawlee hybrid fallback before direct HTML |
