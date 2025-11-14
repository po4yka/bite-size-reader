---
name: api-debugging
description: Debug Firecrawl and OpenRouter API calls including request/response inspection, error handling, and retry logic. Use when investigating external API failures or analyzing API usage patterns.
version: 1.0.0
allowed-tools: Bash, Read, Grep
---

# API Debugging Skill

Helps debug and troubleshoot Firecrawl and OpenRouter API integrations.

## Firecrawl API

### Endpoints
- **Base URL**: `https://api.firecrawl.dev`
- **Scrape endpoint**: `POST /v1/scrape`

### Official Documentation
- **Features**: https://docs.firecrawl.dev/features/scrape
- **API Reference**: https://docs.firecrawl.dev/api-reference/endpoint/scrape
- **Advanced Guide**: https://docs.firecrawl.dev/advanced-scraping-guide

### Integration Location
- **Client**: `app/adapters/content/content_extractor.py`
- **Parser**: `app/adapters/external/firecrawl_parser.py`
- **DB Storage**: `crawl_results` table

### Common Request Format

```json
{
  "url": "https://example.com/article",
  "formats": ["markdown", "html"],
  "mobile": false,
  "parsers": ["pdf"],
  "timeout": 30000
}
```

### Debugging Failed Crawls

```bash
# Check crawl results for specific request
sqlite3 /data/app.db << EOF
.mode json
SELECT
  request_id,
  source_url,
  status,
  firecrawl_success,
  firecrawl_error_code,
  firecrawl_error_message,
  http_status,
  latency_ms
FROM crawl_results
WHERE request_id = '<correlation_id>';
EOF
```

### Common Error Codes

- **400**: Invalid request (bad URL, malformed params)
- **401**: Invalid API key
- **402**: Payment required (quota exceeded)
- **429**: Rate limit exceeded
- **500/502/503**: Firecrawl server errors (retry with backoff)
- **timeout**: Request exceeded timeout limit

### Retry Logic

Check `app/adapters/content/content_extractor.py`:
- 3 retries with exponential backoff on 5xx/timeout
- Toggle `mobile` emulation on PDF failures
- Check `parsers` configuration

### Enable Debug Logging

```bash
# Set environment variable
export DEBUG_PAYLOADS=1
export LOG_LEVEL=DEBUG

# Then run and check logs for request/response previews
# (Authorization headers are automatically redacted)
```

### Test Firecrawl Directly

```bash
curl -X POST https://api.firecrawl.dev/v1/scrape \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "formats": ["markdown"]
  }' | python -m json.tool
```

## OpenRouter API

### Endpoints
- **Base URL**: `https://openrouter.ai`
- **Chat completions**: `POST /api/v1/chat/completions`

### Official Documentation
- **Overview**: https://openrouter.ai/docs/api-reference/overview
- **Chat Completions**: https://openrouter.ai/docs/api-reference/chat-completion
- **Quickstart**: https://openrouter.ai/docs/quickstart

### Integration Location
- **Client**: `app/adapters/openrouter/openrouter_client.py`
- **Request Builder**: `app/adapters/openrouter/request_builder.py`
- **Response Processor**: `app/adapters/openrouter/response_processor.py`
- **Error Handler**: `app/adapters/openrouter/error_handler.py`
- **DB Storage**: `llm_calls` table

### Common Request Format

```json
{
  "model": "openai/gpt-4",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant..."},
    {"role": "user", "content": "Summarize this article..."}
  ],
  "temperature": 0.3,
  "response_format": {"type": "json_object"}
}
```

### Debugging Failed LLM Calls

```bash
# Check LLM calls for specific request
sqlite3 /data/app.db << EOF
.mode json
SELECT
  id,
  model,
  status,
  tokens_prompt,
  tokens_completion,
  cost_usd,
  latency_ms,
  error_text,
  created_at
FROM llm_calls
WHERE request_id = '<correlation_id>'
ORDER BY created_at;
EOF
```

### View Full Request/Response

```bash
# Get request messages
sqlite3 /data/app.db "
  SELECT request_messages_json
  FROM llm_calls
  WHERE request_id = '<correlation_id>'
  LIMIT 1;
" | python -m json.tool

# Get response
sqlite3 /data/app.db "
  SELECT response_json
  FROM llm_calls
  WHERE request_id = '<correlation_id>'
  LIMIT 1;
" | python -m json.tool
```

### Common Error Codes

- **400**: Invalid request (malformed JSON, bad parameters)
- **401**: Invalid API key
- **402**: Insufficient credits
- **429**: Rate limit exceeded
- **500/502/503**: OpenRouter server errors (retry with backoff)
- **Context length exceeded**: Prompt too long for model

### Model Fallback Chain

Check `app/adapters/openrouter/error_handler.py`:
- Primary model configured in `OPENROUTER_MODEL`
- Fallback cascade for structured output failures
- Long-context model support for large articles

### Enable Debug Payloads

```bash
export DEBUG_PAYLOADS=1
export LOG_LEVEL=DEBUG

# Run bot or CLI - payloads will be logged with Authorization redacted
```

### Test OpenRouter Directly

```bash
curl -X POST https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -H "HTTP-Referer: $OPENROUTER_HTTP_REFERER" \
  -H "X-Title: $OPENROUTER_X_TITLE" \
  -d '{
    "model": "openai/gpt-4",
    "messages": [
      {"role": "user", "content": "Hello, world!"}
    ]
  }' | python -m json.tool
```

## Rate Limiting & Concurrency

### Configuration

```bash
# Max concurrent API calls (default: 4)
export MAX_CONCURRENT_CALLS=4

# Request timeout (default: 60 seconds)
export REQUEST_TIMEOUT_SEC=60
```

### Check Concurrency Implementation

See `app/adapters/content/url_processor.py`:
- Semaphore-based rate limiting
- Concurrent calls for chunked content
- Sequential processing for multi-URL requests

## Common Debugging Scenarios

### 1. "Firecrawl returns empty content"

Check:
```bash
# View raw response
sqlite3 /data/app.db "
  SELECT raw_response_json
  FROM crawl_results
  WHERE request_id = '<correlation_id>';
" | python -m json.tool

# Check if PDF parser needed
grep -r "parsers.*pdf" app/adapters/content/
```

### 2. "LLM returns invalid JSON"

Check `app/core/json_utils.py`:
- Uses `json_repair` library to fix malformed output
- Falls back through multiple parsing strategies
- Logs repair attempts with correlation ID

### 3. "Rate limit errors"

```bash
# Count recent API calls
sqlite3 /data/app.db "
  SELECT COUNT(*) as calls_last_hour
  FROM llm_calls
  WHERE created_at > datetime('now', '-1 hour');
"
```

### 4. "High API costs"

```bash
# Analyze token usage and costs
sqlite3 /data/app.db << EOF
.mode column
.headers on
SELECT
  model,
  COUNT(*) as calls,
  AVG(tokens_prompt) as avg_prompt,
  AVG(tokens_completion) as avg_completion,
  SUM(cost_usd) as total_cost
FROM llm_calls
WHERE status = 'ok'
GROUP BY model
ORDER BY total_cost DESC;
EOF
```

## Environment Variables Reference

```bash
# Firecrawl
FIRECRAWL_API_KEY=fc-...

# OpenRouter
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=openai/gpt-4
OPENROUTER_HTTP_REFERER=https://github.com/po4yka/bite-size-reader
OPENROUTER_X_TITLE=Bite-Size Reader

# Debugging
DEBUG_PAYLOADS=1
LOG_LEVEL=DEBUG
```

## Important Notes

- **Authorization redaction**: All auth headers are stripped before DB storage
- **Full payload logging**: Both request and response are persisted (even on error)
- **Correlation IDs**: Essential for tracing API calls end-to-end
- **Retry logic**: Exponential backoff prevents thundering herd
- **Cost tracking**: Every successful call logs tokens and estimated cost
