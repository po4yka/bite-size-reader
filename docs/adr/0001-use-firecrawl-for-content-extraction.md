# ADR-0001: Use Firecrawl for Content Extraction

**Date:** 2024-12-15

**Status:** Accepted

**Deciders:** po4yka

**Technical Story:** Initial architecture decision for web content extraction

## Context

Bite-Size Reader needs to extract clean, structured content from web articles for LLM summarization. Web scraping presents several challenges:

1. **JavaScript Rendering**: Modern sites often require JavaScript execution to render content
2. **Anti-Bot Protection**: Many sites employ Cloudflare, rate limiting, or CAPTCHA
3. **Content Cleanliness**: HTML contains navigation, ads, sidebars that dilute summary quality
4. **Proxy Management**: Rotating proxies needed to avoid IP bans
5. **Maintenance Burden**: Web scraping code requires constant updates as sites change
6. **LLM Token Costs**: Unfiltered HTML bloats token usage and degrades summary quality

The project requires a solution that provides:

- Clean, markdown-formatted article content
- JavaScript rendering capabilities
- Built-in anti-bot bypass (proxies, user agents, headers)
- Low maintenance overhead
- Reasonable cost for single-user deployment

## Decision

We will use **Firecrawl API** (https://firecrawl.dev/) as the primary content extraction service for web articles.

Firecrawl is a managed web scraping API that:

- Renders JavaScript-heavy sites
- Bypasses anti-bot protections using rotating proxies
- Extracts clean markdown content (removes ads, navigation, footers)
- Provides structured output (title, description, metadata, markdown)
- Offers a generous free tier (500 credits/month) + pay-as-you-go pricing
- Requires minimal code (single API call)

**Implementation**: `app/adapters/content/content_extractor.py` wraps the Firecrawl `/scrape` endpoint.

## Consequences

### Positive

- **Zero Maintenance**: No need to maintain scraping infrastructure, proxies, or anti-bot logic
- **High Success Rate**: Firecrawl handles Cloudflare, JavaScript, and complex sites reliably
- **Clean Content**: Markdown output significantly improves LLM summary quality
- **Cost-Effective**: Free tier covers ~500 articles/month; paid tier is $25/month for 5,000 credits
- **Structured Metadata**: Provides title, description, keywords, and favicon URLs out-of-box
- **Fallback Resilience**: Errors are API-level (predictable), not site-specific (brittle)

### Negative

- **External Dependency**: Project depends on Firecrawl's uptime and pricing
- **Latency**: API calls add 2-5s latency compared to direct HTTP requests
- **Rate Limits**: Free tier limits daily usage (500 credits total, not daily)
- **No Offline Mode**: Requires internet connectivity and valid API key
- **Limited Customization**: Cannot fine-tune extraction logic per-site
- **Cost Scaling**: High-volume usage (>5,000 articles/month) becomes expensive

### Neutral

- Firecrawl responses are persisted in `crawl_results` table for debugging and caching
- Correlation IDs (`request_id`) tie together Telegram messages, crawl results, and LLM calls
- All responses stored regardless of success/failure for observability

## Alternatives Considered

### Alternative 1: Trafilatura (Self-Hosted)

Trafilatura is an open-source Python library for content extraction.

**Pros:**

- No API costs or rate limits
- Offline-capable
- Lightweight and fast (< 1s per URL)
- Good extraction quality for static sites

**Cons:**

- No JavaScript rendering (misses React/Vue/Angular apps)
- No proxy rotation (IP bans inevitable)
- No anti-bot bypass (fails on Cloudflare-protected sites)
- Requires constant maintenance as sites change
- Lower extraction quality than Firecrawl

**Why not chosen**: Fails on JavaScript-heavy and Cloudflare-protected sites, which are increasingly common. Maintenance burden too high for single-person project.

### Alternative 2: Newspaper3k

Python library for article extraction.

**Pros:**

- Open-source and free
- Good for news sites
- Extracts publish dates, authors

**Cons:**

- **Abandoned Project**: Last update 2019, incompatible with Python 3.10+
- No JavaScript rendering
- No proxy support
- Limited site coverage

**Why not chosen**: Unmaintained and doesn't meet modern web scraping requirements.

### Alternative 3: Playwright + BeautifulSoup (Custom Solution)

Build custom scraper using Playwright (browser automation) + BeautifulSoup (HTML parsing).

**Pros:**

- Full control over extraction logic
- No API costs
- Can handle JavaScript rendering
- Can implement site-specific scrapers

**Cons:**

- **High Maintenance**: Requires ongoing updates as sites change
- **Infrastructure Overhead**: Need to run headless browser (memory-intensive)
- **Proxy Management**: Must build and maintain proxy rotation logic
- **Anti-Bot Bypass**: Need to implement fingerprint randomization, CAPTCHA solving
- **Development Time**: Weeks of work to reach Firecrawl's reliability

**Why not chosen**: Maintenance burden and development time too high for a single-user project. Firecrawl solves these problems for $25/month.

### Alternative 4: ScrapingBee / ScraperAPI

Competing managed scraping APIs.

**Pros:**

- Similar features to Firecrawl (JavaScript rendering, proxies, anti-bot)
- Comparable pricing

**Cons:**

- **Less Markdown Focus**: Firecrawl specializes in clean markdown extraction
- **Worse Free Tier**: ScrapingBee offers 1,000 API credits (vs Firecrawl's 500 scrapes)
- **Less LLM-Optimized**: Firecrawl explicitly targets LLM use cases

**Why not chosen**: Firecrawl provides better markdown quality and is optimized for LLM pipelines.

## Decision Criteria

Criteria used to evaluate alternatives (in priority order):

1. **Extraction Quality** (High): Must provide clean, LLM-friendly content
2. **JavaScript Support** (High): Must handle modern web apps
3. **Anti-Bot Bypass** (High): Must work on Cloudflare-protected sites
4. **Maintenance Burden** (High): Must require minimal ongoing work
5. **Cost** (Medium): Should fit within single-user budget (~$25/month)
6. **Reliability** (Medium): Should have >99% uptime
7. **Latency** (Low): Acceptable if < 10s per article

Firecrawl scored highest across all high-priority criteria.

## Related Decisions

- [ADR-0002](0002-strict-json-summary-contract.md) - Strict JSON contract requires clean input
- Content fallback logic in `app/core/content_cleaner.py` handles Firecrawl failures

## Implementation Notes

- **Code**: `app/adapters/content/content_extractor.py` (`ContentExtractor` class)
- **API Endpoint**: `POST https://api.firecrawl.dev/v1/scrape`
- **Configuration**: `FIRECRAWL_API_KEY` environment variable (required)
- **Rate Limiting**: Semaphore-based concurrency control (`MAX_CONCURRENT_CALLS=3`)
- **Error Handling**: Retry logic with exponential backoff (3 attempts)
- **Persistence**: All responses stored in `crawl_results` table with `correlation_id`

**Firecrawl Documentation**: https://docs.firecrawl.dev/api-reference/endpoint/scrape

## Notes

**2025-01-15**: Added trafilatura as fallback for Firecrawl failures (see `content_cleaner.py`)

**2025-02-05**: Observed 95%+ success rate across 500+ articles. Primary failures due to paywalled content (WSJ, NYT), not Firecrawl limitations.

---

### Update Log

| Date | Author | Change |
|------|--------|--------|
| 2024-12-15 | po4yka | Initial decision (Accepted) |
| 2025-01-15 | po4yka | Added fallback note |
| 2025-02-05 | po4yka | Added success rate observation |
