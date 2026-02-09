# How to Optimize Performance

Tune Bite-Size Reader for speed, cost, and resource efficiency.

**Audience:** Operators
**Difficulty:** Intermediate
**Estimated Time:** 20 minutes

---

## Performance Goals

Choose your optimization target:

- **Speed**: Faster summaries (<5s vs 10s+)
- **Cost**: Lower API costs ($10/month vs $30/month)
- **Resources**: Lower RAM/CPU usage (512MB vs 2GB)

---

## Quick Wins

### 1. Use Faster LLM Models

**Impact**: 50-70% faster summarization

```bash
# Fast & cheap models
OPENROUTER_MODEL=qwen/qwen3-max              # Fastest, good quality
# OPENROUTER_MODEL=google/gemini-2.0-flash-001:free  # Free, fast

# Fallback to fast models
OPENROUTER_FALLBACK_MODELS=qwen/qwen3-max,google/gemini-2.0-flash-001:free
```

**Benchmark** (avg time per summary):

- DeepSeek V3: ~8-10s
- Qwen 3 Max: ~4-6s
- Gemini 2.0 Flash: ~3-5s

---

### 2. Enable Redis Caching

**Impact**: 40-60% cost reduction for repeated URLs

```bash
REDIS_ENABLED=true
REDIS_URL=redis://localhost:6379/0
REDIS_CACHE_TTL_SECONDS=3600  # 1 hour
```

**Hit rate**: 30-40% for users who re-read articles.

See: [Setup Redis Caching](setup-redis-caching.md)

---

### 3. Increase Concurrency

**Impact**: 2-3x throughput for batch processing

```bash
# Default: 4 concurrent requests
MAX_CONCURRENT_CALLS=6  # Increase for better throughput

# Warning: May hit rate limits
```

**Recommendation**: Start with 6, increase to 10 if no rate limiting.

---

### 4. Disable Optional Features

**Impact**: 20-30% faster, lower token costs

```bash
# Disable web search (adds ~500 tokens + 1-3 API calls)
WEB_SEARCH_ENABLED=false

# Disable two-pass insights generation
SUMMARY_TWO_PASS_ENABLED=false

# Disable YouTube video download (keep transcript)
YOUTUBE_DOWNLOAD_VIDEO=false
YOUTUBE_DOWNLOAD_TRANSCRIPT=true
```

---

## Speed Optimization

### LLM Selection

```bash
# Fastest models (ranked)
1. google/gemini-2.0-flash-001:free  # Free, 2-4s
2. qwen/qwen3-max                    # $0.02, 3-5s
3. deepseek/deepseek-v3.2            # $0.01, 6-8s

# Avoid slow models
# claude-opus-4: ~15-20s
# gpt-4-turbo: ~12-15s
```

### Reduce Content Length

```bash
# Limit max tokens sent to LLM
MAX_CONTENT_LENGTH_TOKENS=30000  # Default: 50000

# Enable chunking for long articles
CHUNKING_ENABLED=true
CHUNK_MAX_CHARS=150000  # Default: 200000
```

### Optimize Firecrawl

```bash
# Reduce JavaScript wait time
FIRECRAWL_WAIT_FOR_MS=1000  # Default: 3000

# Reduce timeout
FIRECRAWL_TIMEOUT_SEC=60  # Default: 90

# Skip unnecessary content
FIRECRAWL_INCLUDE_IMAGES=false
FIRECRAWL_INCLUDE_LINKS=false
```

---

## Cost Optimization

### Use Free Models

```bash
# Free tier models (zero cost)
OPENROUTER_MODEL=google/gemini-2.0-flash-001:free
OPENROUTER_FALLBACK_MODELS=deepseek/deepseek-r1:free

# Check OpenRouter for current free models
# https://openrouter.ai/models?order=newest&max_price=0
```

### Minimize Token Usage

```bash
# Reduce max tokens in LLM response
OPENROUTER_MAX_TOKENS=2000  # Default: none (unlimited)

# Use lower temperature (more deterministic, faster)
OPENROUTER_TEMPERATURE=0.1  # Default: 0.2

# Enable prompt caching (Gemini, Claude)
OPENROUTER_ENABLE_PROMPT_CACHING=true
```

### Aggressive Caching

```bash
# Enable all caches
REDIS_ENABLED=true
ENABLE_FIRECRAWL_CACHE=true
ENABLE_LLM_CACHE=true

# Long cache TTL (7 days)
REDIS_CACHE_TTL_SECONDS=604800
```

### Firecrawl Free Tier Strategy

```bash
# Use trafilatura fallback for simple sites
CONTENT_EXTRACTION_FALLBACK=true

# Firecrawl only for complex sites
# (Auto-detects JavaScript-heavy pages)
```

---

## Resource Optimization

### Reduce Memory Usage

```bash
# Use smallest embedding model
CHROMA_EMBEDDING_MODEL=all-MiniLM-L6-v2  # 90 MB

# Disable ChromaDB if not using search
ENABLE_CHROMA=false

# Limit ChromaDB memory
CHROMA_MAX_MEMORY_MB=256

# Reduce Redis connections
REDIS_MAX_CONNECTIONS=5  # Default: 10
```

### CPU Optimization

```bash
# Force CPU for embeddings (if GPU unavailable)
CHROMA_DEVICE=cpu

# Reduce embedding batch size
CHROMA_BATCH_SIZE=10  # Default: 50

# Disable token counting (use approximation)
TOKEN_COUNTING_MODE=fast  # len(text)//4 approximation
```

### Disk Space Management

```bash
# YouTube auto-cleanup
YOUTUBE_AUTO_CLEANUP_DAYS=3  # Delete after 3 days
YOUTUBE_MAX_STORAGE_GB=5     # Max 5 GB

# Database vacuum (reclaim space)
sqlite3 data/app.db "VACUUM;"
```

---

## Benchmarking

### Measure Baseline

```bash
# Test summary speed
time python -m app.cli.summary --url https://example.com/article

# Example output:
# real    0m8.234s
# user    0m2.145s
# sys     0m0.234s
```

### Monitor Metrics

```bash
# Database query performance
sqlite3 data/app.db "
  SELECT
    ROUND(AVG(total_processing_time_sec), 2) as avg_time_sec,
    MIN(total_processing_time_sec) as min_time_sec,
    MAX(total_processing_time_sec) as max_time_sec
  FROM requests
  WHERE created_at > datetime('now', '-7 days');
"

# API costs
sqlite3 data/app.db "
  SELECT
    COUNT(*) as total_calls,
    SUM(tokens_used) as total_tokens
  FROM llm_calls
  WHERE created_at > datetime('now', '-30 days');
"
```

---

## Performance Profiles

### Minimal (Low Resources)

```bash
# Target: 512 MB RAM, minimal cost
OPENROUTER_MODEL=google/gemini-2.0-flash-001:free
MAX_CONCURRENT_CALLS=2
ENABLE_CHROMA=false
REDIS_ENABLED=false
WEB_SEARCH_ENABLED=false
YOUTUBE_DOWNLOAD_ENABLED=false
```

### Balanced (Production)

```bash
# Target: 1 GB RAM, ~$15/month
OPENROUTER_MODEL=qwen/qwen3-max
MAX_CONCURRENT_CALLS=4
ENABLE_CHROMA=true
REDIS_ENABLED=true
WEB_SEARCH_ENABLED=false
YOUTUBE_DOWNLOAD_ENABLED=true
CHROMA_EMBEDDING_MODEL=all-MiniLM-L6-v2
```

### High Performance (No Cost Constraints)

```bash
# Target: 2 GB RAM, ~$50/month, <3s summaries
OPENROUTER_MODEL=qwen/qwen3-max
MAX_CONCURRENT_CALLS=10
ENABLE_CHROMA=true
REDIS_ENABLED=true
WEB_SEARCH_ENABLED=true
YOUTUBE_DOWNLOAD_ENABLED=true
CHROMA_EMBEDDING_MODEL=all-mpnet-base-v2
CHROMA_DEVICE=cuda  # If GPU available
```

---

## Monitoring

### Track Performance

```bash
# Average processing time (last 7 days)
sqlite3 data/app.db "
  SELECT ROUND(AVG(total_processing_time_sec), 2) as avg_sec
  FROM requests
  WHERE created_at > datetime('now', '-7 days');
"

# Slow requests (>15s)
sqlite3 data/app.db "
  SELECT url, total_processing_time_sec
  FROM requests
  WHERE total_processing_time_sec > 15
  ORDER BY total_processing_time_sec DESC
  LIMIT 10;
"
```

### Track Costs

```bash
# Token usage (last 30 days)
sqlite3 data/app.db "
  SELECT
    SUM(prompt_tokens) as total_prompt,
    SUM(completion_tokens) as total_completion,
    SUM(total_tokens) as total
  FROM llm_calls
  WHERE created_at > datetime('now', '-30 days');
"

# Estimated cost (DeepSeek: $0.14/1M prompt, $0.28/1M completion)
# Total cost = (prompt_tokens * 0.14 + completion_tokens * 0.28) / 1,000,000
```

---

## Troubleshooting Performance Issues

### Slow Summaries (>15s)

**Diagnose:**

```bash
# Check which step is slow
LOG_LEVEL=DEBUG
docker restart bite-size-reader

# Look for timing logs
docker logs bite-size-reader | grep -i "took\|elapsed\|duration"
```

**Common causes:**

1. **Slow Firecrawl** (JavaScript-heavy sites): Use faster timeout, try trafilatura fallback
2. **Slow LLM** (large content): Use chunking, reduce max tokens
3. **Network latency**: Check internet connection, try different provider

---

### High Memory Usage

**Diagnose:**

```bash
# Check memory usage
docker stats bite-size-reader

# Or system-wide
htop  # or top
```

**Solutions:**

- Disable ChromaDB or use smaller model
- Reduce Redis connection pool
- Reduce concurrent calls

---

### High API Costs

**Diagnose:**

```bash
# Check token usage per model
sqlite3 data/app.db "
  SELECT
    model,
    COUNT(*) as calls,
    SUM(total_tokens) as tokens
  FROM llm_calls
  GROUP BY model
  ORDER BY tokens DESC;
"
```

**Solutions:**

- Switch to cheaper/free models
- Enable caching
- Disable web search
- Reduce content length

---

## See Also

- [FAQ § Performance](../FAQ.md#performance)
- [FAQ § Cost Optimization](../FAQ.md#cost-optimization)
- [environment_variables.md](../environment_variables.md) - All performance variables
- [TROUBLESHOOTING § Performance Issues](../TROUBLESHOOTING.md#performance-issues)

---

**Last Updated:** 2026-02-09
