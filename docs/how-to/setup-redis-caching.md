# How to Setup Redis Caching

Enable Redis for caching, rate limiting, and distributed locking.

**Audience:** Operators
**Difficulty:** Intermediate
**Estimated Time:** 10 minutes

---

## What Redis Provides

Redis adds optional caching and coordination:

- **Response caching**: Firecrawl and LLM responses (avoid re-processing same URLs)
- **API rate limiting**: Protect Mobile API from abuse
- **Distributed locking**: Coordinate background tasks across multiple instances
- **Sync coordination**: Multi-device sync conflict resolution

**Performance impact**: 30-40% cache hit rate for users who re-read articles.

**Graceful degradation**: Bot continues without Redis if unavailable (caching disabled).

---

## Prerequisites

- Bite-Size Reader installed and running
- Redis 6.0+ (recommend Redis 7.x)

---

## Steps

### 1. Install Redis

**Option A: Docker (Recommended)**

```bash
# Start Redis container
docker run -d \
  --name redis \
  -p 6379:6379 \
  --restart unless-stopped \
  redis:7-alpine

# Verify running
docker ps | grep redis
```

**Option B: macOS (Homebrew)**

```bash
# Install
brew install redis

# Start service
brew services start redis

# Verify
redis-cli ping
# Should return: PONG
```

**Option C: Ubuntu/Debian**

```bash
# Install
sudo apt-get update
sudo apt-get install redis-server

# Start service
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Verify
redis-cli ping
# Should return: PONG
```

---

### 2. Configure Connection

Add to your `.env` file:

**Simple (Local Redis)**:

```bash
REDIS_ENABLED=true
REDIS_URL=redis://localhost:6379/0
```

**Advanced (Custom Host/Port)**:

```bash
REDIS_ENABLED=true
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your_password  # If auth enabled
REDIS_SSL=false
```

**Redis Cloud/Managed Service**:

```bash
REDIS_ENABLED=true
REDIS_URL=redis://username:password@hostname:port/db
REDIS_SSL=true
```

---

### 3. Configure Cache Settings

```bash
# Cache TTL (time-to-live)
REDIS_CACHE_TTL_SECONDS=3600  # 1 hour default

# Connection pool
REDIS_MAX_CONNECTIONS=10
REDIS_SOCKET_TIMEOUT=5
REDIS_SOCKET_CONNECT_TIMEOUT=5

# Enable specific caches
ENABLE_FIRECRAWL_CACHE=true
ENABLE_LLM_CACHE=true
ENABLE_SEARCH_CACHE=true
```

---

### 4. Restart Bot

```bash
# Docker
docker restart bite-size-reader

# Local
python bot.py
```

---

## Verification

### Test Redis Connection

```bash
# Test connection
redis-cli ping
# Should return: PONG

# Check Redis info
redis-cli INFO server

# Monitor Redis in real-time
redis-cli MONITOR
# (Press Ctrl+C to stop)
```

### Test Caching

1. **Send a URL to bot** (first time, no cache):

   ```
   https://example.com/article
   ```

   - Check logs: "Cache miss" or "Storing in cache"

2. **Send same URL again** (should use cache):

   ```
   https://example.com/article
   ```

   - Check logs: "Cache hit"
   - Response should be faster (~2-3s vs 8-10s)

3. **Verify cache keys in Redis**:

   ```bash
   # List all keys
   redis-cli KEYS "*"

   # Count cache entries
   redis-cli DBSIZE

   # Check specific cache entry
   redis-cli GET "firecrawl:cache:https://example.com/article"
   ```

---

## Cache Management

### View Cache Statistics

```bash
# Cache hit/miss stats
redis-cli INFO stats | grep hits

# Memory usage
redis-cli INFO memory | grep used_memory_human

# Key count
redis-cli DBSIZE
```

### Clear Cache

```bash
# Flush all cache
redis-cli FLUSHALL

# Flush specific database
redis-cli FLUSHDB

# Delete keys by pattern
redis-cli --scan --pattern "firecrawl:cache:*" | xargs redis-cli DEL

# Delete specific key
redis-cli DEL "llm:cache:request_hash"
```

### Set Custom TTL

```bash
# Via environment variable (applies to all)
REDIS_CACHE_TTL_SECONDS=7200  # 2 hours

# Or set per-key via redis-cli
redis-cli EXPIRE "key_name" 3600  # 1 hour
```

---

## Troubleshooting

### Connection refused

**Symptom:** Warning logs "Failed to connect to Redis"

**Solution:**

```bash
# Check if Redis is running
redis-cli ping

# If not running, start it
# Docker:
docker start redis

# macOS:
brew services start redis

# Linux:
sudo systemctl start redis-server

# Verify connection settings in .env
grep REDIS_URL .env
```

---

### Authentication failed

**Symptom:** Error "NOAUTH Authentication required"

**Solution:**

```bash
# Update .env with password
REDIS_URL=redis://:password@localhost:6379/0

# Or use separate password variable
REDIS_PASSWORD=your_password
```

---

### Cache not working

**Symptom:** Same URL processed multiple times (no cache hits)

**Diagnostics:**

```bash
# Check if Redis is enabled
grep REDIS_ENABLED .env
# Should show: REDIS_ENABLED=true

# Monitor Redis commands
redis-cli MONITOR
# Send URL to bot, verify GET/SET commands appear

# Check logs
docker logs bite-size-reader | grep -i cache
```

**Common causes:**

1. `REDIS_ENABLED=false` in config
2. Redis connection failed (bot falls back to no-cache mode)
3. Cache TTL too short (expired before second request)

---

### High memory usage

**Symptom:** Redis consuming too much RAM

**Solution:**

```bash
# Check memory usage
redis-cli INFO memory

# Set max memory limit
redis-cli CONFIG SET maxmemory 100mb
redis-cli CONFIG SET maxmemory-policy allkeys-lru

# Or in redis.conf:
maxmemory 100mb
maxmemory-policy allkeys-lru

# Reduce cache TTL
REDIS_CACHE_TTL_SECONDS=1800  # 30 minutes
```

---

## Advanced Configuration

### Redis Persistence

**RDB (Snapshots)**:

```bash
# redis.conf
save 900 1      # Save after 900s if 1 key changed
save 300 10     # Save after 300s if 10 keys changed
save 60 10000   # Save after 60s if 10000 keys changed
```

**AOF (Append-Only File)**:

```bash
# redis.conf
appendonly yes
appendfsync everysec  # Sync every second
```

**Recommendation**: Use RDB for caching (data loss acceptable), AOF for sync locks (data loss not acceptable).

### Redis Cluster (High Availability)

For multi-instance deployments:

```bash
# .env
REDIS_CLUSTER_ENABLED=true
REDIS_CLUSTER_NODES=node1:6379,node2:6379,node3:6379
```

### Distributed Locking

For background task coordination:

```bash
# Enable Redis-based distributed locks
BACKGROUND_REDIS_LOCK_ENABLED=true
BACKGROUND_REDIS_LOCK_REQUIRED=false  # Fail if Redis unavailable (false = graceful degradation)
BACKGROUND_LOCK_TTL_MS=300000  # 5 minutes
```

---

## Performance Tuning

### Connection Pooling

```bash
# Increase pool size for high concurrency
REDIS_MAX_CONNECTIONS=20
REDIS_MIN_IDLE_CONNECTIONS=5
```

### Timeout Settings

```bash
# Reduce timeouts for faster failover
REDIS_SOCKET_TIMEOUT=3
REDIS_SOCKET_CONNECT_TIMEOUT=3
REDIS_SOCKET_KEEPALIVE=true
```

### Cache Key Prefixes

Organize cache by type:

```bash
REDIS_KEY_PREFIX=bsr:  # All keys prefixed with "bsr:"
FIRECRAWL_CACHE_PREFIX=firecrawl:
LLM_CACHE_PREFIX=llm:
```

---

## Monitoring

### Redis Metrics

```bash
# Key metrics
redis-cli INFO stats

# Hit rate
redis-cli INFO stats | grep keyspace_hits
redis-cli INFO stats | grep keyspace_misses

# Memory usage over time
watch -n 1 'redis-cli INFO memory | grep used_memory_human'

# Slow queries (>10ms)
redis-cli SLOWLOG GET 10
```

### Integration with Monitoring Tools

**Prometheus:**

```bash
# Use redis_exporter
docker run -d -p 9121:9121 oliver006/redis_exporter \
  --redis.addr=redis://localhost:6379
```

**Grafana Dashboard:**

- Import dashboard ID 763 (Redis Dashboard for Prometheus)

---

## Disable Redis (Rollback)

```bash
# Set to false in .env
REDIS_ENABLED=false

# Restart bot
docker restart bite-size-reader

# Bot falls back to no-cache mode (no functional impact)
```

---

## See Also

- [FAQ § Redis](../FAQ.md)
- [TROUBLESHOOTING § Redis Issues](../TROUBLESHOOTING.md#redis-issues)
- [environment_variables.md § Redis](../environment_variables.md)
- [DEPLOYMENT.md](../DEPLOYMENT.md) - Production Redis setup

---

**Last Updated:** 2026-02-09
