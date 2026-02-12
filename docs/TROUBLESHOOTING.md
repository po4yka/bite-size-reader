# Troubleshooting Guide

This guide helps you diagnose and resolve common issues with Bite-Size Reader.

## Table of Contents

- [Debugging with Correlation IDs](#debugging-with-correlation-ids)
- [Installation Issues](#installation-issues)
- [Configuration Issues](#configuration-issues)
- [Firecrawl Issues](#firecrawl-issues)
- [OpenRouter Issues](#openrouter-issues)
- [YouTube Issues](#youtube-issues)
- [Database Issues](#database-issues)
- [Redis Issues](#redis-issues)
- [ChromaDB Issues](#chromadb-issues)
- [Mobile API Issues](#mobile-api-issues)
- [MCP Server Issues](#mcp-server-issues)
- [Performance Issues](#performance-issues)
- [Debugging Strategies](#debugging-strategies)

---

## Debugging with Correlation IDs

**Correlation IDs are your best debugging tool.** Every request in Bite-Size Reader gets a unique `correlation_id` that ties together:

- Telegram messages
- Database requests
- Firecrawl API calls
- OpenRouter LLM calls
- Log entries

### How to Find Correlation IDs

1. **From Error Messages**: All user-facing errors include `Error ID: <correlation_id>`

   ```
   ❌ Failed to summarize article.
   Error ID: a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6
   ```

2. **From Logs**: Search logs for the error message, find the correlation_id

   ```bash
   grep "a1b2c3d4" /var/log/bite-size-reader/app.log
   ```

3. **From Database**: Query the `requests` table

   ```sql
   SELECT * FROM requests WHERE id = 'a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6';
   ```

### Using Correlation IDs

Once you have a correlation ID:

```sql
-- See the full request details
SELECT * FROM requests WHERE id = '<correlation_id>';

-- See Firecrawl response
SELECT * FROM crawl_results WHERE request_id = '<correlation_id>';

-- See LLM calls (prompt, response, errors)
SELECT * FROM llm_calls WHERE request_id = '<correlation_id>';

-- See final summary
SELECT * FROM summaries WHERE request_id = '<correlation_id>';

-- See Telegram messages
SELECT * FROM telegram_messages WHERE request_id = '<correlation_id>';
```

**Pro Tip**: Use `DEBUG_PAYLOADS=1` to log full request/response bodies (Authorization headers redacted).

---

## Installation Issues

### Python Version Mismatch

**Symptom**: `ImportError` or syntax errors when running the bot.

**Cause**: Python 3.13+ required, older version installed.

**Solution**:

```bash
python3 --version  # Should be 3.13 or higher
# If not, install Python 3.13+ and recreate venv
pyenv install 3.13.0
pyenv local 3.13.0
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Missing ffmpeg

**Symptom**: YouTube downloads fail with `ffmpeg not found`.

**Cause**: yt-dlp requires ffmpeg for video/audio merging.

**Solution**:

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get update && sudo apt-get install -y ffmpeg

# Verify
ffmpeg -version
```

### Dependency Installation Failures

**Symptom**: `pip install` fails with compilation errors (especially on ARM/M1 Macs).

**Cause**: Some packages (like chromadb, sentence-transformers) require system libraries.

**Solution**:

```bash
# macOS (M1/M2)
brew install cmake pkg-config

# Ubuntu/Debian
sudo apt-get install -y build-essential python3-dev

# Then retry
pip install -r requirements.txt
```

### Pre-commit Hook Failures

**Symptom**: `git commit` fails with pre-commit errors.

**Cause**: Code doesn't pass ruff formatting or mypy type checks.

**Solution**:

```bash
# Auto-fix formatting issues
make format

# Check what's still failing
make lint
make type

# If you need to bypass hooks temporarily (NOT recommended)
git commit --no-verify
```

---

## Configuration Issues

### Missing Required Environment Variables

**Symptom**: Bot fails to start with `KeyError` or `ValidationError`.

**Cause**: Required env vars not set in `.env` file.

**Solution**:

```bash
# Check which vars are missing
python -c "from app.config.settings import RuntimeConfig; RuntimeConfig()"

# Add missing vars to .env
cat >> .env << EOF
API_ID=your_api_id
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
ALLOWED_USER_IDS=123456789
FIRECRAWL_API_KEY=your_key
OPENROUTER_API_KEY=your_key
EOF
```

See [environment_variables.md](environment_variables.md) for full reference.

### Invalid API Keys

**Symptom**: Bot starts but all summaries fail with "401 Unauthorized" or "Invalid API key".

**Cause**: Expired, revoked, or mistyped API keys.

**Solution**:

```bash
# Test Firecrawl key
curl -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
     https://api.firecrawl.dev/v1/scrape \
     -d '{"url":"https://example.com"}'

# Test OpenRouter key
curl -H "Authorization: Bearer $OPENROUTER_API_KEY" \
     https://openrouter.ai/api/v1/models

# If invalid, regenerate keys:
# - Firecrawl: https://firecrawl.dev/account
# - OpenRouter: https://openrouter.ai/keys
```

### Access Denied (User Not Whitelisted)

**Symptom**: Bot replies "Access denied" when you message it.

**Cause**: Your Telegram user ID not in `ALLOWED_USER_IDS`.

**Solution**:

```bash
# Find your Telegram user ID
# Method 1: Message @userinfobot on Telegram

# Method 2: Check bot logs when you message it
grep "Access denied" /var/log/bite-size-reader/app.log
# Look for: "user_id": 987654321

# Add to .env
echo "ALLOWED_USER_IDS=123456789,987654321" >> .env

# Restart bot
docker restart bite-size-reader
```

---

## Firecrawl Issues

### API Rate Limits

**Symptom**: "429 Too Many Requests" errors.

**Cause**: Exceeded Firecrawl rate limits (free tier: 500 credits/month, paid: varies).

**Solution**:

```bash
# Check Firecrawl usage
curl -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
     https://api.firecrawl.dev/v1/account

# Upgrade plan or wait for monthly reset
# https://firecrawl.dev/pricing
```

### Firecrawl Timeouts

**Symptom**: Summaries fail with "Timeout waiting for Firecrawl response".

**Cause**: Slow websites or Firecrawl server overload.

**Solution**:

```bash
# Increase timeout (default: 30s)
echo "FIRECRAWL_TIMEOUT_SECONDS=60" >> .env

# Restart bot
docker restart bite-size-reader
```

### Proxy Failures

**Symptom**: Firecrawl returns "Failed to fetch" for specific sites.

**Cause**: Site blocked Firecrawl's proxies or requires authentication.

**Solution**:

1. **Check if site is paywalled**: WSJ, NYT, Medium (members-only) fail even with Firecrawl
2. **Try different proxy**: Firecrawl rotates automatically, retry may work
3. **Fallback to trafilatura**: Set `CONTENT_EXTRACTION_FALLBACK=true` to use local extraction

### Content Extraction Failures

**Symptom**: Summary says "No content extracted" or "Article too short".

**Cause**: Firecrawl returned HTML but no clean markdown (e.g., SPAs, JavaScript errors).

**Solution**:

```bash
# Enable DEBUG_PAYLOADS to see raw Firecrawl response
echo "DEBUG_PAYLOADS=1" >> .env

# Check database for Firecrawl response
sqlite3 data/app.db "SELECT * FROM crawl_results WHERE request_id = '<correlation_id>';"

# If Firecrawl failed, enable fallback
echo "CONTENT_EXTRACTION_FALLBACK=true" >> .env
```

---

## OpenRouter Issues

### Model Selection Errors

**Symptom**: Summaries fail with "Model not found" or "Model is offline".

**Cause**: Specified model unavailable or deprecated.

**Solution**:

```bash
# Check available models
curl https://openrouter.ai/api/v1/models | jq '.data[] | {id, name}'

# Update to working model
echo "OPENROUTER_MODEL=deepseek/deepseek-v3.2" >> .env
echo "OPENROUTER_FALLBACK_MODELS=qwen/qwen3-max,moonshotai/kimi-k2.5" >> .env

# Restart bot
docker restart bite-size-reader
```

### Rate Limiting

**Symptom**: "429 Rate Limit Exceeded" errors.

**Cause**: Too many concurrent requests or exceeded daily quota.

**Solution**:

```bash
# Reduce concurrency
echo "MAX_CONCURRENT_CALLS=2" >> .env  # Default: 3

# Add rate limit delay
echo "RATE_LIMIT_DELAY_SECONDS=1.0" >> .env

# Check OpenRouter dashboard for usage
# https://openrouter.ai/account
```

### Token Limit Exceeded

**Symptom**: Summaries fail with "Token limit exceeded" or "Context length exceeded".

**Cause**: Article too long for model's context window.

**Solution**:

```bash
# Use long-context model
echo "OPENROUTER_LONG_CONTEXT_MODEL=moonshotai/kimi-k2.5" >> .env  # 256k context

# Or enable chunking (splits long articles)
echo "ENABLE_CONTENT_CHUNKING=true" >> .env
echo "MAX_CHUNK_SIZE_TOKENS=50000" >> .env

# Restart bot
docker restart bite-size-reader
```

### Fallback Chain Failures

**Symptom**: "All models failed" error after trying fallbacks.

**Cause**: Primary and all fallback models failed (offline, rate-limited, or broken).

**Solution**:

```bash
# Check logs for specific model errors
grep "model failed" /var/log/bite-size-reader/app.log

# Update fallback chain to reliable models
echo "OPENROUTER_FALLBACK_MODELS=qwen/qwen3-max,google/gemini-2.0-flash-001:free" >> .env

# Verify models are online
curl https://openrouter.ai/api/v1/models | jq '.data[] | select(.id | contains("qwen")) | {id, pricing}'
```

### JSON Parsing Failures

**Symptom**: "Failed to parse summary JSON" even after retries.

**Cause**: Model producing invalid JSON or missing required fields.

**Solution**:

```bash
# Enable JSON repair fallback
echo "ENABLE_JSON_REPAIR=true" >> .env

# Try different model (some models better at JSON)
echo "OPENROUTER_MODEL=qwen/qwen3-max" >> .env  # Qwen is excellent at JSON

# Enable structured outputs (if model supports)
echo "OPENROUTER_ENABLE_STRUCTURED_OUTPUTS=true" >> .env

# Check actual LLM response in database
sqlite3 data/app.db "SELECT response FROM llm_calls WHERE request_id = '<correlation_id>';"
```

---

## YouTube Issues

### yt-dlp Not Found

**Symptom**: YouTube downloads fail with "yt-dlp not found".

**Cause**: yt-dlp not installed.

**Solution**:

```bash
pip install yt-dlp

# Or via system package manager
# macOS
brew install yt-dlp

# Ubuntu/Debian
sudo curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp
sudo chmod a+rx /usr/local/bin/yt-dlp
```

### Transcript Unavailable

**Symptom**: "No transcript available for this video".

**Cause**: Video lacks auto-generated or manual captions.

**Solution**:

- YouTube only: Use audio transcription (requires `WHISPER_API_KEY` or local Whisper)
- Or: Use video download + audio extraction workflow (not implemented yet)

```bash
# Option 1: Enable Whisper transcription (if available)
echo "ENABLE_WHISPER_TRANSCRIPTION=true" >> .env
echo "WHISPER_API_KEY=your_key" >> .env

# Option 2: Skip video if no transcript
# (Default behavior: fails gracefully with error message)
```

### Storage Quota Exceeded

**Symptom**: YouTube downloads fail with "Disk full" or "No space left on device".

**Cause**: Downloaded videos fill up `YOUTUBE_DOWNLOAD_PATH` directory.

**Solution**:

```bash
# Check disk usage
du -sh /data/youtube_downloads/

# Clean old downloads
find /data/youtube_downloads/ -type f -mtime +7 -delete

# Or configure auto-cleanup
echo "YOUTUBE_AUTO_CLEANUP_DAYS=7" >> .env  # Delete after 7 days
echo "YOUTUBE_MAX_STORAGE_GB=10" >> .env    # Max 10 GB storage

# Restart bot
docker restart bite-size-reader
```

### Format/Quality Issues

**Symptom**: Downloaded video has poor quality or wrong format.

**Cause**: Default format selection doesn't match availability.

**Solution**:

```bash
# Force 1080p (default)
echo "YOUTUBE_VIDEO_QUALITY=1080" >> .env

# Or accept lower quality if 1080p unavailable
echo "YOUTUBE_VIDEO_QUALITY=720" >> .env

# Change format
echo "YOUTUBE_VIDEO_FORMAT=mp4" >> .env  # Default: mp4

# Restart bot
docker restart bite-size-reader
```

---

## Database Issues

### Database Locked

**Symptom**: "Database is locked" errors during writes.

**Cause**: Multiple processes accessing SQLite concurrently (not supported well).

**Solution**:

```bash
# Increase timeout
echo "DB_TIMEOUT=30" >> .env  # Default: 5 seconds

# Or use WAL mode (Write-Ahead Logging)
sqlite3 data/app.db "PRAGMA journal_mode=WAL;"

# Verify
sqlite3 data/app.db "PRAGMA journal_mode;"
# Should return: wal
```

### Corruption

**Symptom**: "Database disk image is malformed" or "database corruption".

**Cause**: Unclean shutdown, disk full, or hardware failure.

**Solution**:

```bash
# Check integrity
sqlite3 data/app.db "PRAGMA integrity_check;"

# If corrupted, restore from backup
cp data/app.db data/app.db.corrupted
cp data/backups/app.db.backup data/app.db

# If no backup, try to recover
sqlite3 data/app.db ".recover" | sqlite3 data/app.db.recovered
mv data/app.db.recovered data/app.db
```

**Prevention**: Enable automatic backups:

```bash
echo "DB_AUTO_BACKUP=true" >> .env
echo "DB_BACKUP_INTERVAL_HOURS=24" >> .env
```

### Migration Failures

**Symptom**: Bot fails to start after update with "Schema version mismatch".

**Cause**: Database schema out of date.

**Solution**:

```bash
# Run migrations
python -m app.cli.migrate_db

# Or force recreate (WARNING: deletes all data)
rm data/app.db
python -m app.cli.migrate_db

# Restore data from backup if needed
sqlite3 data/app.db < data/backups/app.db.backup.sql
```

### Performance Issues

**Symptom**: Slow queries, high CPU usage from database.

**Cause**: Missing indexes or large tables.

**Solution**:

```bash
# Rebuild indexes
python -m app.cli.rebuild_indexes

# Vacuum database (reclaim space, rebuild indexes)
sqlite3 data/app.db "VACUUM;"

# Analyze query performance
sqlite3 data/app.db "EXPLAIN QUERY PLAN SELECT * FROM summaries WHERE url = 'example.com';"
```

---

## Redis Issues

### Connection Failures

**Symptom**: "Failed to connect to Redis" warnings.

**Cause**: Redis not running or wrong connection settings.

**Solution**:

```bash
# Check if Redis is running
redis-cli ping
# Should return: PONG

# If not running, start Redis
# macOS
brew services start redis

# Ubuntu/Debian
sudo systemctl start redis

# Docker
docker run -d -p 6379:6379 redis:7-alpine

# Update connection settings
echo "REDIS_URL=redis://localhost:6379/0" >> .env
echo "REDIS_TIMEOUT=5" >> .env

# Restart bot
docker restart bite-size-reader
```

### Graceful Degradation

**Symptom**: Bot works but logs Redis errors.

**Cause**: Redis optional (caching only), bot continues without it.

**Solution**:

- **If Redis not needed**: Disable it entirely

  ```bash
  echo "ENABLE_REDIS=false" >> .env
  ```

- **If needed**: Fix connection (see above)

### Cache Invalidation

**Symptom**: Stale data returned from cache.

**Cause**: Cache not invalidated after updates.

**Solution**:

```bash
# Flush all cache
redis-cli FLUSHALL

# Or flush specific keys
redis-cli KEYS "summary:*" | xargs redis-cli DEL

# Adjust cache TTL
echo "REDIS_CACHE_TTL_SECONDS=3600" >> .env  # Default: 1 hour
```

---

## ChromaDB Issues

### Connection Failures

**Symptom**: Search fails with "Failed to connect to ChromaDB".

**Cause**: ChromaDB server not running or wrong URL.

**Solution**:

```bash
# Check if ChromaDB is running
curl http://localhost:8000/api/v1/heartbeat

# If not, start ChromaDB
# Docker
docker run -d -p 8000:8000 chromadb/chroma:latest

# Or local
chroma run --host localhost --port 8000

# Update connection settings
echo "CHROMA_HOST=localhost" >> .env
echo "CHROMA_PORT=8000" >> .env

# Restart bot
docker restart bite-size-reader
```

### Embedding Errors

**Symptom**: Search fails with "Failed to generate embeddings".

**Cause**: Sentence-transformers model not downloaded or GPU issues.

**Solution**:

```bash
# Download embedding model manually
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# If GPU issues, force CPU
echo "CHROMA_DEVICE=cpu" >> .env

# Or try different embedding model
echo "CHROMA_EMBEDDING_MODEL=all-mpnet-base-v2" >> .env

# Restart bot
docker restart bite-size-reader
```

### Collection Not Found

**Symptom**: "Collection 'summaries' does not exist".

**Cause**: ChromaDB database not initialized or wiped.

**Solution**:

```bash
# Recreate collection and backfill embeddings
python -m app.cli.backfill_chroma_store

# Check collection exists
curl http://localhost:8000/api/v1/collections

# Verify count
curl http://localhost:8000/api/v1/collections/summaries/count
```

---

## Mobile API Issues

### JWT Authentication Errors

**Symptom**: "Invalid token" or "Token expired" errors.

**Cause**: Expired JWT token or mismatched secret.

**Solution**:

```bash
# Verify JWT_SECRET is set
grep JWT_SECRET .env

# If missing, generate new secret
openssl rand -hex 32
echo "JWT_SECRET=<generated_secret>" >> .env

# Restart API
docker restart bite-size-reader

# Client: Re-authenticate to get new token
curl -X POST http://localhost:8000/v1/auth/telegram-login \
     -H "Content-Type: application/json" \
     -d '{"telegram_user_id": 123456789, "telegram_auth_token": "..."}'
```

### Sync Conflicts

**Symptom**: "Sync conflict detected" errors during sync.

**Cause**: Client and server modified same data, conflict resolution failed.

**Solution**:

```bash
# Enable conflict logging
echo "SYNC_CONFLICT_LOGGING=debug" >> .env

# Check logs for conflict details
grep "sync conflict" /var/log/bite-size-reader/app.log

# Client: Force full sync (discards local changes)
curl -X POST http://localhost:8000/v1/sync/summaries?mode=full \
     -H "Authorization: Bearer <token>"
```

### Rate Limiting

**Symptom**: "429 Too Many Requests" from mobile API.

**Cause**: Exceeded API rate limits (default: 100 req/min per user).

**Solution**:

```bash
# Increase rate limit
echo "API_RATE_LIMIT_PER_MINUTE=200" >> .env

# Or disable rate limiting (not recommended for production)
echo "API_ENABLE_RATE_LIMIT=false" >> .env

# Restart API
docker restart bite-size-reader
```

---

## MCP Server Issues

### Connection Failures

**Symptom**: Claude Desktop can't connect to MCP server.

**Cause**: MCP server not running or wrong configuration in Claude config.

**Solution**:

1. **Start MCP server**:

   ```bash
   python -m app.cli.mcp_server
   ```

2. **Verify Claude config** (`~/Library/Application Support/Claude/claude_desktop_config.json`):

   ```json
   {
     "mcpServers": {
       "bite-size-reader": {
         "command": "python",
         "args": ["-m", "app.cli.mcp_server"],
         "cwd": "/path/to/bite-size-reader",
         "env": {
           "PYTHONPATH": "/path/to/bite-size-reader"
         }
       }
     }
   }
   ```

3. **Restart Claude Desktop**

### Tool Execution Errors

**Symptom**: "Tool failed to execute" in Claude Desktop.

**Cause**: MCP tool encountered error (database issue, missing env vars, etc.).

**Solution**:

```bash
# Enable MCP debug logging
echo "MCP_LOG_LEVEL=DEBUG" >> .env

# Check MCP server logs
tail -f /var/log/bite-size-reader/mcp.log

# If using SSE, ensure user scoping is configured
echo "MCP_TRANSPORT=sse" >> .env
echo "MCP_USER_ID=123456789" >> .env
```

---

## Performance Issues

### Slow Summarization

**Symptom**: Summaries take >30 seconds to generate.

**Cause**: Slow LLM model, large article, or network latency.

**Solution**:

```bash
# Use faster model
echo "OPENROUTER_MODEL=qwen/qwen3-max" >> .env  # Faster than DeepSeek

# Reduce context window
echo "MAX_CONTENT_LENGTH_TOKENS=30000" >> .env  # Default: 50000

# Enable content chunking
echo "ENABLE_CONTENT_CHUNKING=true" >> .env

# Increase concurrency
echo "MAX_CONCURRENT_CALLS=5" >> .env  # Default: 3

# Restart bot
docker restart bite-size-reader
```

### High Memory Usage

**Symptom**: Bot crashes with "Out of memory" or high RAM usage.

**Cause**: Large embedding models or ChromaDB in-memory storage.

**Solution**:

```bash
# Use smaller embedding model
echo "CHROMA_EMBEDDING_MODEL=all-MiniLM-L6-v2" >> .env  # Smallest, still good quality

# Limit ChromaDB memory
echo "CHROMA_MAX_MEMORY_MB=512" >> .env

# Disable ChromaDB if not needed
echo "ENABLE_CHROMA=false" >> .env

# Restart bot with memory limit (Docker)
docker run --memory=1g bite-size-reader
```

### Token Counting Overhead

**Symptom**: High CPU usage during token counting.

**Cause**: tiktoken encoding/decoding for every request.

**Solution**:

```bash
# Use faster token estimation (less accurate but much faster)
echo "TOKEN_COUNTING_MODE=fast" >> .env  # Uses len(text)//4 approximation

# Or reduce token counting frequency
echo "TOKEN_COUNTING_CACHE_SIZE=1000" >> .env

# Restart bot
docker restart bite-size-reader
```

---

## Debugging Strategies

### 1. Start Simple

Before diving deep:

1. **Check bot is running**: `docker ps` or `pgrep -f bot.py`
2. **Check logs**: `docker logs bite-size-reader` or `tail -f /var/log/bite-size-reader/app.log`
3. **Test basic command**: Send `/start` to bot, verify it responds

### 2. Enable Debug Logging

```bash
# Enable debug logging
echo "LOG_LEVEL=DEBUG" >> .env

# Enable payload logging (redacts Authorization headers)
echo "DEBUG_PAYLOADS=1" >> .env

# Restart bot
docker restart bite-size-reader

# Watch logs in real-time
docker logs -f bite-size-reader
```

### 3. Use CLI Tools

Test components in isolation:

```bash
# Test URL summarization (bypasses Telegram)
python -m app.cli.summary --url https://example.com/article

# Test search
python -m app.cli.search --query "python tutorial"

# Test database
sqlite3 data/app.db "SELECT COUNT(*) FROM summaries;"

# Test ChromaDB
python -m app.cli.backfill_chroma_store --dry-run
```

### 4. Inspect Database

Use correlation IDs to trace requests:

```bash
sqlite3 data/app.db

-- Find failed requests
SELECT id, url, status, error FROM requests WHERE status = 'failed' LIMIT 10;

-- See Firecrawl responses
SELECT request_id, status_code, success FROM crawl_results WHERE success = 0;

-- See LLM failures
SELECT request_id, model, error FROM llm_calls WHERE error IS NOT NULL;

-- See summary validation errors
SELECT request_id, validation_errors FROM summaries WHERE validation_errors IS NOT NULL;
```

### 5. Test External APIs Manually

Isolate whether issue is with bot or external service:

```bash
# Test Firecrawl
curl -X POST https://api.firecrawl.dev/v1/scrape \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}' | jq .

# Test OpenRouter
curl -X POST https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek/deepseek-v3.2",
    "messages": [{"role": "user", "content": "Hello"}]
  }' | jq .
```

### 6. Compare Working vs Broken

If something used to work:

```bash
# Check git history for changes
git log --oneline --since="2 weeks ago"

# Diff config files
git diff HEAD~10 .env

# Check if environment changed (Python version, dependencies)
pip list | grep -i firecrawl

# Rollback to last working version
git checkout <commit_hash>
docker build -t bite-size-reader .
docker run bite-size-reader
```

### 7. Minimal Reproduction

Strip down to simplest failing case:

1. Test with single, simple URL (not complex SPA or paywalled site)
2. Disable optional features (web search, ChromaDB, Redis)
3. Use minimal config (only required env vars)
4. Test with default models (not experimental or unstable models)

### 8. Check System Resources

```bash
# Disk space
df -h

# Memory
free -h

# CPU
top -bn1 | grep "Cpu(s)"

# Network
ping -c 3 api.firecrawl.dev
ping -c 3 openrouter.ai
```

---

## Getting Help

If you're still stuck after trying these steps:

1. **Gather diagnostics**:
   - Correlation ID
   - Relevant log excerpts
   - Database query results (requests, llm_calls, crawl_results)
   - Environment configuration (redact API keys!)

2. **Check existing issues**: [GitHub Issues](https://github.com/po4yka/bite-size-reader/issues)

3. **Open new issue** with:
   - Clear title (e.g., "Firecrawl timeouts on all URLs")
   - Steps to reproduce
   - Expected vs actual behavior
   - Diagnostics from step 1
   - Version info (`git rev-parse HEAD`)

4. **Include correlation ID** in issue title/description for faster debugging

---

## Related Documentation

- [environment_variables.md](environment_variables.md) - Full configuration reference
- [DEPLOYMENT.md](DEPLOYMENT.md) - Setup and deployment guides
- [FAQ.md](FAQ.md) - Frequently asked questions
- [SPEC.md](SPEC.md) - Technical specification
- [ADRs](adr/README.md) - Architecture decision records

---

**Last Updated**: 2026-02-09
