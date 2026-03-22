# Firecrawl v2 Separate Compose Stack

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy Firecrawl v2 as a standalone Docker Compose stack at `/home/po4yka/firecrawl/` and reconnect the BSR bot to it via a shared Docker bridge network.

**Architecture:** Firecrawl v2 requires five services (API, Playwright, Redis, RabbitMQ, PostgreSQL) that live in their own compose project. BSR and Firecrawl share a dedicated external Docker network (`firecrawl_net`) so the BSR bot can reach `http://firecrawl-api:3002` via container DNS. The Firecrawl API is also bound to `127.0.0.1:3003` for host-level debugging.

**Tech Stack:** Docker Compose, `ghcr.io/firecrawl/firecrawl` (digest-pinned), `ghcr.io/firecrawl/playwright-service:latest`, `redis:alpine`, `rabbitmq:3-management`, `postgres:17-alpine`

**Hardware constraints:** Raspberry Pi 5, 4 cores, ~9.8 GiB available RAM. All resource limits are tuned for this.

---

## Context

### Why a separate stack?

Firecrawl v2 (`ghcr.io/firecrawl/firecrawl`) requires RabbitMQ, PostgreSQL, and a Playwright microservice. Adding five new containers to BSR's `docker-compose.yml` would bloat it and mix concerns. A separate compose project gives independent lifecycle management.

### Cross-stack networking

Docker Compose projects are isolated by default. The solution is a named external bridge network `firecrawl_net`:

- Both stacks declare it as `external: true`
- BSR bot reaches `http://firecrawl-api:3002` via Docker DNS
- No host port needed for internal communication (host port 3003 is for debug only)

### Firecrawl v2 PostgreSQL

The Firecrawl API detects `NUQ_DATABASE_URL`. If set, it skips Docker-in-Docker and connects directly. We supply a dedicated `postgres:17-alpine` container. Firecrawl handles schema init on first startup.

### Current state of BSR compose

`bsr-firecrawl` service exists in `/home/po4yka/bite-size-reader/docker-compose.yml` with:

- `restart: "no"` (disabled)
- `image: ghcr.io/firecrawl/firecrawl@sha256:90a10e...` (correct image, wrong config)
- `FIRECRAWL_SELF_HOSTED_URL=http://firecrawl:3002` (needs updating to `firecrawl-api`)

---

## Task 1: Create the shared Docker network

**Files:**

- No files — pure Docker command

**Step 1: Create the external bridge network**

```bash
docker network create firecrawl_net
```

Expected output: a network ID hash (64 hex chars).

**Step 2: Verify it exists**

```bash
docker network ls --filter name=firecrawl_net
```

Expected: one row with `firecrawl_net` and driver `bridge`.

---

## Task 2: Create the firecrawl compose project directory

**Files:**

- Create: `/home/po4yka/firecrawl/` (directory)
- Create: `/home/po4yka/firecrawl/.env`
- Create: `/home/po4yka/firecrawl/docker-compose.yml`

**Step 1: Create the directory**

```bash
mkdir -p /home/po4yka/firecrawl
```

**Step 2: Create `.env`**

Create `/home/po4yka/firecrawl/.env` with this content:

```dotenv
# Firecrawl v2 stack configuration
# Do not commit this file — it contains credentials.

# PostgreSQL (internal to firecrawl stack)
POSTGRES_USER=firecrawl
POSTGRES_PASSWORD=firecrawl_local_secret
POSTGRES_DB=firecrawl

# Firecrawl API key (must match FIRECRAWL_API_KEY in BSR .env)
FIRECRAWL_API_KEY=fc-bsr-local

# RabbitMQ
RABBITMQ_DEFAULT_USER=firecrawl
RABBITMQ_DEFAULT_PASS=firecrawl_rabbit

# Worker concurrency (keep low on Pi 5 — 4 cores)
NUM_WORKERS_PER_QUEUE=2
CRAWL_CONCURRENT_REQUESTS=4
MAX_CONCURRENT_JOBS=3
BROWSER_POOL_SIZE=2
```

**Step 3: Create `docker-compose.yml`**

Create `/home/po4yka/firecrawl/docker-compose.yml` with this content:

```yaml
# Firecrawl v2 — standalone compose stack
# Connects to BSR via the external "firecrawl_net" bridge network.
# To start:  docker compose up -d
# To stop:   docker compose down
# Network setup (one-time): docker network create firecrawl_net

name: firecrawl

x-common-env: &common-env
  REDIS_URL: redis://firecrawl-redis:6379
  REDIS_RATE_LIMIT_URL: redis://firecrawl-redis:6379
  PLAYWRIGHT_MICROSERVICE_URL: http://firecrawl-playwright:3000/scrape
  POSTGRES_USER: ${POSTGRES_USER:-firecrawl}
  POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-firecrawl_local_secret}
  POSTGRES_DB: ${POSTGRES_DB:-firecrawl}
  POSTGRES_HOST: firecrawl-postgres
  POSTGRES_PORT: 5432
  NUQ_DATABASE_URL: postgres://${POSTGRES_USER:-firecrawl}:${POSTGRES_PASSWORD:-firecrawl_local_secret}@firecrawl-postgres:5432/${POSTGRES_DB:-firecrawl}
  NUQ_RABBITMQ_URL: amqp://${RABBITMQ_DEFAULT_USER:-firecrawl}:${RABBITMQ_DEFAULT_PASS:-firecrawl_rabbit}@firecrawl-rabbitmq:5672
  USE_DB_AUTHENTICATION: "false"
  NUM_WORKERS_PER_QUEUE: ${NUM_WORKERS_PER_QUEUE:-2}
  CRAWL_CONCURRENT_REQUESTS: ${CRAWL_CONCURRENT_REQUESTS:-4}
  MAX_CONCURRENT_JOBS: ${MAX_CONCURRENT_JOBS:-3}
  BROWSER_POOL_SIZE: ${BROWSER_POOL_SIZE:-2}
  BULL_AUTH_KEY: ${FIRECRAWL_API_KEY:-fc-bsr-local}
  TEST_API_KEY: ${FIRECRAWL_API_KEY:-fc-bsr-local}

services:
  api:
    # Pinned by digest — same image verified working in BSR stack.
    # To update: docker pull ghcr.io/firecrawl/firecrawl:latest, update digest.
    image: ghcr.io/firecrawl/firecrawl@sha256:90a10e0053d78f36308c46a7fbb84d6d8258ec1da13fa08e6b821bd650d5e569
    container_name: firecrawl-api
    init: true
    environment:
      <<: *common-env
      HOST: "0.0.0.0"
      PORT: 3002
      INTERNAL_PORT: 3002
      ENV: local
    command: ["node", "dist/src/harness.js"]
    ports:
      # Host debug access only — BSR uses Docker DNS (firecrawl-api:3002)
      - "127.0.0.1:3003:3002"
    depends_on:
      firecrawl-redis:
        condition: service_healthy
      firecrawl-rabbitmq:
        condition: service_healthy
      firecrawl-postgres:
        condition: service_healthy
      firecrawl-playwright:
        condition: service_started
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://localhost:3002/v1/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 90s
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: "1.50"
        reservations:
          memory: 512M
          cpus: "0.50"
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    networks:
      - internal
      - firecrawl_net
    security_opt:
      - no-new-privileges:true

  firecrawl-playwright:
    image: ghcr.io/firecrawl/playwright-service:latest
    container_name: firecrawl-playwright
    init: true
    environment:
      PORT: 3000
      MAX_CONCURRENT_PAGES: ${CRAWL_CONCURRENT_REQUESTS:-4}
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: "1.00"
        reservations:
          memory: 256M
          cpus: "0.25"
    tmpfs:
      - /tmp/.cache:noexec,nosuid,size=512m
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    networks:
      - internal
    security_opt:
      - no-new-privileges:true

  firecrawl-redis:
    image: redis:alpine
    container_name: firecrawl-redis
    command: redis-server --bind 0.0.0.0 --save "" --appendonly no
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: "0.25"
    logging:
      driver: "json-file"
      options:
        max-size: "5m"
        max-file: "2"
    networks:
      - internal
    security_opt:
      - no-new-privileges:true

  firecrawl-rabbitmq:
    image: rabbitmq:3-management
    container_name: firecrawl-rabbitmq
    environment:
      RABBITMQ_DEFAULT_USER: ${RABBITMQ_DEFAULT_USER:-firecrawl}
      RABBITMQ_DEFAULT_PASS: ${RABBITMQ_DEFAULT_PASS:-firecrawl_rabbit}
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "check_running"]
      interval: 15s
      timeout: 10s
      retries: 5
      start_period: 30s
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: "0.50"
    logging:
      driver: "json-file"
      options:
        max-size: "5m"
        max-file: "2"
    networks:
      - internal
    security_opt:
      - no-new-privileges:true

  firecrawl-postgres:
    image: postgres:17-alpine
    container_name: firecrawl-postgres
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-firecrawl}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-firecrawl_local_secret}
      POSTGRES_DB: ${POSTGRES_DB:-firecrawl}
    volumes:
      - firecrawl_postgres_data:/var/lib/postgresql/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-firecrawl} -d ${POSTGRES_DB:-firecrawl}"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 30s
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: "0.50"
    logging:
      driver: "json-file"
      options:
        max-size: "5m"
        max-file: "2"
    networks:
      - internal
    security_opt:
      - no-new-privileges:true

networks:
  internal:
    driver: bridge
  firecrawl_net:
    name: firecrawl_net
    external: true

volumes:
  firecrawl_postgres_data:
```

**Step 4: Verify the file is valid YAML**

```bash
docker compose -f /home/po4yka/firecrawl/docker-compose.yml config --quiet
```

Expected: no output, exit code 0.

---

## Task 3: Pull the Playwright service image

**Step 1: Pull**

```bash
docker pull ghcr.io/firecrawl/playwright-service:latest
```

Expected: `Status: Downloaded newer image` or `Status: Image is up to date`.

If this fails (manifest unknown), the Playwright image is not pre-published. In that case, skip to the fallback step.

**Step 2 (fallback only): Build playwright service from source**

Only if Step 1 failed:

```bash
git clone --depth=1 https://github.com/mendableai/firecrawl.git /tmp/firecrawl-src
docker build -t ghcr.io/firecrawl/playwright-service:latest /tmp/firecrawl-src/apps/playwright-service-ts
```

Then update the image reference in `docker-compose.yml`:

```yaml
firecrawl-playwright:
  image: ghcr.io/firecrawl/playwright-service:latest
```

(It's already this value, no change needed if build succeeds.)

---

## Task 4: Start the firecrawl stack

**Step 1: Bring up all services**

```bash
docker compose --env-file /home/po4yka/firecrawl/.env \
  -f /home/po4yka/firecrawl/docker-compose.yml up -d
```

Expected: five containers created/started — `firecrawl-postgres`, `firecrawl-redis`, `firecrawl-rabbitmq`, `firecrawl-playwright`, `firecrawl-api`.

**Step 2: Wait for all to reach healthy state (up to 2 minutes)**

```bash
watch -n5 'docker ps --format "table {{.Names}}\t{{.Status}}" | grep firecrawl'
```

Expected final state: all five containers `(healthy)` or `Up`. Press Ctrl-C when stable.

**Step 3: Smoke-test the API**

```bash
curl -fsS http://127.0.0.1:3003/v1/health
```

Expected: JSON response with `{"status":"ok"}` or similar 2xx body.

If health check uses a different path, check logs:

```bash
docker logs firecrawl-api --tail 30
```

Look for the port the server announces, then adjust the health check URL.

**Step 4: Verify the API key works**

```bash
curl -fsS http://127.0.0.1:3003/v1/scrape \
  -H "Authorization: Bearer fc-bsr-local" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com","formats":["markdown"]}' | head -c 200
```

Expected: JSON with `"success":true` and a `data` block containing markdown.

---

## Task 5: Update BSR compose to use shared network and new container name

**Files:**

- Modify: `/home/po4yka/bite-size-reader/docker-compose.yml`

**Step 1: Read the current networks section (bottom of file)**

```bash
grep -n "networks:" /home/po4yka/bite-size-reader/docker-compose.yml
```

The file currently has:

```yaml
networks:
  karakeep:
    name: karakeep_default
    external: true
```

**Step 2: Edit the file — three changes**

**Change A:** Add `firecrawl_net` to the global networks block (line ~293):

Old:

```yaml
networks:
  karakeep:
    name: karakeep_default
    external: true
```

New:

```yaml
networks:
  karakeep:
    name: karakeep_default
    external: true
  firecrawl_net:
    name: firecrawl_net
    external: true
```

**Change B:** Add `firecrawl_net` to the `bsr` service networks (it currently only has `default` and `karakeep`):

Find in the `bsr:` service block:

```yaml
    networks:
      - default
      - karakeep
```

Change to:

```yaml
    networks:
      - default
      - karakeep
      - firecrawl_net
```

**Change C:** Update the `FIRECRAWL_SELF_HOSTED_URL` env var in the `bsr:` service:

Old:

```yaml
      - FIRECRAWL_SELF_HOSTED_URL=http://firecrawl:3002
```

New:

```yaml
      - FIRECRAWL_SELF_HOSTED_URL=http://firecrawl-api:3002
```

**Step 3: Validate the compose file**

```bash
MCP_USER_ID=94225168 docker compose \
  --env-file /home/po4yka/bite-size-reader/.env \
  -f /home/po4yka/bite-size-reader/docker-compose.yml \
  config --quiet
```

Expected: exit code 0, no output.

**Step 4: Commit the BSR compose changes**

```bash
git -C /home/po4yka/bite-size-reader add docker-compose.yml
git -C /home/po4yka/bite-size-reader commit -m \
  "feat(compose): connect bsr to firecrawl v2 via shared network"
```

---

## Task 6: Remove the dead firecrawl stub from BSR compose

The `firecrawl:` service entry in BSR's `docker-compose.yml` is now obsolete — the real service lives in the firecrawl stack. Remove it.

**Files:**

- Modify: `/home/po4yka/bite-size-reader/docker-compose.yml`

**Step 1: Remove the entire `firecrawl:` service block**

The block spans from `firecrawl:` through `stop_grace_period: 30s` (approximately lines 180–213). Delete the entire block including the `depends_on` reference inside `bsr:` and `mobile-api:`.

The `bsr:` service depends_on block currently has:

```yaml
      firecrawl:
        condition: service_healthy
        required: false # Graceful degradation -- Scrapling works without it
```

Remove just those three lines. Firecrawl health is now managed by the external stack; BSR should not gate on it.

**Step 2: Validate**

```bash
MCP_USER_ID=94225168 docker compose \
  --env-file /home/po4yka/bite-size-reader/.env \
  -f /home/po4yka/bite-size-reader/docker-compose.yml \
  config --quiet
```

**Step 3: Commit**

```bash
git -C /home/po4yka/bite-size-reader add docker-compose.yml
git -C /home/po4yka/bite-size-reader commit -m \
  "chore(compose): remove dead firecrawl stub service from bsr stack"
```

---

## Task 7: Redeploy BSR bot and end-to-end smoke test

**Step 1: Recreate the `bsr` container (picks up new network)**

```bash
MCP_USER_ID=94225168 docker compose \
  --env-file /home/po4yka/bite-size-reader/.env \
  -f /home/po4yka/bite-size-reader/docker-compose.yml \
  up -d --no-deps bsr
```

**Step 2: Verify bsr is on the firecrawl_net network**

```bash
docker inspect bsr-bot --format '{{json .NetworkSettings.Networks}}' | jq 'keys'
```

Expected output includes `"firecrawl_net"`.

**Step 3: Verify bsr can reach firecrawl-api via DNS**

```bash
docker exec bsr-bot curl -fsS http://firecrawl-api:3002/v1/health
```

Expected: `{"status":"ok"}` or similar.

**Step 4: Verify bsr is healthy**

```bash
sleep 15 && docker ps --format 'table {{.Names}}\t{{.Status}}' | grep bsr
```

Expected: `bsr-bot` shows `(healthy)`.

**Step 5: Set FIRECRAWL_SELF_HOSTED_ENABLED=true in BSR .env**

The `.env` at `/home/po4yka/bite-size-reader/.env` needs:

```
FIRECRAWL_SELF_HOSTED_ENABLED=true
```

If it's currently `false` or `0`, set it to `true`, then recreate the container (repeat Step 1).

**Step 6: Full scrape smoke test**

```bash
docker exec bsr-bot python -m app.cli.summary \
  --url https://example.com \
  --log-level DEBUG 2>&1 | tail -30
```

Expected: JSON summary output, logs showing `scraper=firecrawl` or Scrapling/Defuddle as fallback. No fatal errors.

---

## Rollback

If firecrawl-api is unhealthy and causing issues:

```bash
# Stop firecrawl stack
docker compose -f /home/po4yka/firecrawl/docker-compose.yml down

# BSR continues running — FIRECRAWL_SELF_HOSTED_ENABLED=false degrades gracefully
```

The scraper chain falls back to Scrapling → Defuddle → Playwright → Crawlee → direct HTTP automatically.
