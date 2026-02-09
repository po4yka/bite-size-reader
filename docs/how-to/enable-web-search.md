# How to Enable Web Search Enrichment

Add real-time web context to article summaries using web search.

**Audience:** Users, Operators
**Difficulty:** Beginner
**Estimated Time:** 3 minutes

---

## What is Web Search Enrichment?

Web search enrichment uses an LLM to:

1. **Analyze content** and identify knowledge gaps (unfamiliar entities, recent events, claims)
2. **Extract search queries** (max 3) if additional context would help
3. **Search the web** via Firecrawl Search API or DuckDuckGo
4. **Inject results** into summarization prompt for up-to-date context

**When it helps:**

- News articles (time-sensitive topics)
- Research papers (need latest findings)
- Tutorial articles (check if still relevant)

**When to skip:**

- Timeless content (classic literature, historical docs)
- Privacy-sensitive content (internal docs, private blogs)
- Cost-sensitive usage (adds ~500 tokens + 1-3 search API calls per summary)

---

## Prerequisites

- Bite-Size Reader installed and running
- Firecrawl API key (free tier supports search)

---

## Steps

### 1. Enable Web Search

Add to your `.env` file:

```bash
# Enable web search enrichment
WEB_SEARCH_ENABLED=true

# Search provider (default: duckduckgo)
WEB_SEARCH_PROVIDER=duckduckgo  # or: google, firecrawl

# Max search queries per article (default: 3)
WEB_SEARCH_MAX_QUERIES=3

# Max results per query (default: 3)
WEB_SEARCH_MAX_RESULTS=3
```

---

### 2. Configure Search Provider (Optional)

**Option A: DuckDuckGo (Default, Free)**

```bash
WEB_SEARCH_PROVIDER=duckduckgo
# No API key needed
```

**Option B: Google Custom Search (Requires API Key)**

```bash
WEB_SEARCH_PROVIDER=google
GOOGLE_SEARCH_API_KEY=your_key
GOOGLE_SEARCH_ENGINE_ID=your_engine_id
```

Get Google API key:

1. Go to https://console.cloud.google.com/apis/credentials
2. Create credentials → API key
3. Enable Custom Search API
4. Create Custom Search Engine at https://cse.google.com/cse/

**Option C: Firecrawl Search**

```bash
WEB_SEARCH_PROVIDER=firecrawl
# Uses your existing FIRECRAWL_API_KEY
```

---

### 3. Restart Bot

```bash
# Docker
docker restart bite-size-reader

# Local
# Press Ctrl+C to stop, then:
python bot.py
```

---

## Verification

Send an article URL about a recent event:

```
https://example.com/article-about-recent-event
```

**Expected behavior:**

1. Bot replies "📥 Processing article..."
2. If web search triggered, you'll see: "🔍 Enriching with web context..."
3. Summary includes up-to-date information beyond LLM training cutoff

**How to tell if web search was used:**

- Check logs for "Web search triggered" or "Web search skipped"
- Enable `DEBUG_PAYLOADS=1` to see search queries and results

---

## Cost Impact

Web search adds:

- **LLM tokens:** ~500 tokens per article (analysis + query extraction)
- **Search API calls:** 1-3 calls per article (only when triggered)
- **Total extra cost:** ~$0.01 per summary

**Optimization:** Only ~30-40% of articles trigger web search (self-contained content is skipped).

---

## Troubleshooting

### Web search never triggers

**Symptom:** No "🔍 Enriching with web context..." message

**Causes:**

1. **Content is self-contained** (LLM decides search wouldn't help)
2. **Web search disabled** in config

**Solution:**

```bash
# Verify enabled
grep WEB_SEARCH_ENABLED .env
# Should show: WEB_SEARCH_ENABLED=true

# Enable debug logging to see LLM decision
LOG_LEVEL=DEBUG
docker restart bite-size-reader

# Check logs
docker logs bite-size-reader | grep "Web search"
```

---

### Search API errors

**Symptom:** Error message "Web search failed" or "Search API error"

**For DuckDuckGo:**

- Usually rate limiting (100 req/day free tier)
- Wait or switch to Google/Firecrawl

**For Google:**

- Check API key and Custom Search Engine ID
- Verify Custom Search API is enabled
- Check quota at https://console.cloud.google.com/apis/dashboard

**For Firecrawl:**

- Verify `FIRECRAWL_API_KEY` is valid
- Check Firecrawl credit balance

---

### Too many search queries

**Symptom:** High API costs from excessive search

**Solution:**

```bash
# Reduce max queries
WEB_SEARCH_MAX_QUERIES=1
WEB_SEARCH_MAX_RESULTS=2

# Or disable for certain content types
# (Not yet implemented, manual disable/enable for now)
```

---

## Advanced Configuration

### Customize Search Behavior

```bash
# Minimum confidence threshold to trigger search (0-1)
WEB_SEARCH_CONFIDENCE_THRESHOLD=0.7

# Search timeout (seconds)
WEB_SEARCH_TIMEOUT_SEC=10

# Cache search results
REDIS_ENABLED=true  # Caches search results for repeated queries
```

### Provider-Specific Settings

**DuckDuckGo:**

```bash
DUCKDUCKGO_REGION=us-en  # Region code
DUCKDUCKGO_SAFESEARCH=moderate  # off, moderate, strict
```

**Google:**

```bash
GOOGLE_SEARCH_COUNTRY=us
GOOGLE_SEARCH_LANGUAGE=en
```

**Firecrawl:**

```bash
FIRECRAWL_SEARCH_LIMIT=5  # Results per query
```

---

## When to Use Web Search

### ✅ Good Use Cases

- **News articles**: Recent events, breaking news, current affairs
- **Tech tutorials**: Check if libraries/APIs still work
- **Research papers**: Cross-reference latest findings
- **Product reviews**: Verify claims, check for recalls
- **Historical articles**: Add recent developments

### ❌ Skip Web Search For

- **Timeless content**: Classic literature, philosophy, historical docs
- **Private/internal docs**: Company wikis, internal blogs (privacy risk)
- **Math/theory**: Self-contained content that doesn't change
- **Personal notes**: No web context needed
- **Cost-sensitive usage**: Disable if minimizing API costs

---

## Disable Web Search Temporarily

```bash
# In .env
WEB_SEARCH_ENABLED=false

# Restart bot
docker restart bite-size-reader
```

Or use per-request override (future feature):

```
/summarize --no-web-search https://example.com
```

---

## Monitoring Web Search Usage

```bash
# Check how often web search triggers
sqlite3 data/app.db "
  SELECT
    COUNT(*) as total_summaries,
    SUM(CASE WHEN web_search_triggered = 1 THEN 1 ELSE 0 END) as with_search,
    ROUND(AVG(CASE WHEN web_search_triggered = 1 THEN 1.0 ELSE 0.0 END) * 100, 2) as trigger_rate_pct
  FROM summaries
  WHERE created_at > datetime('now', '-30 days');
"

# Check search query costs
sqlite3 data/app.db "
  SELECT
    url,
    web_search_queries,
    web_search_results_count
  FROM summaries
  WHERE web_search_triggered = 1
  ORDER BY created_at DESC
  LIMIT 10;
"
```

---

## See Also

- [FAQ § Web Search](../FAQ.md#web-search)
- [TROUBLESHOOTING § Web Search Issues](../TROUBLESHOOTING.md)
- [environment_variables.md § Web Search](../environment_variables.md)
- [multi_agent_architecture.md](../multi_agent_architecture.md) - WebSearchAgent design

---

**Last Updated:** 2026-02-09
