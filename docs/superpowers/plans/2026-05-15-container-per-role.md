# Container-Per-Role Process Supervision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate shell-backgrounded Taskiq processes inside the bot container by splitting bot, worker, scheduler, and migration into separate Docker Compose services, each with independent healthcheck, restart policy, and `RATATOSKR_PROCESS_ROLE`.

**Architecture:** A one-shot `migrate` service runs `python -m app.cli.migrate_db` and exits; `ratatoskr`, `worker`, `scheduler`, and `mobile-api` declare `depends_on: migrate: condition: service_completed_successfully` so no app process starts before schema is current. The `Dockerfile` CMD becomes a single `CMD ["python", "-m", "bot"]`; the `taskiq worker` and `taskiq scheduler` commands are expressed as explicit `command:` overrides in their dedicated Compose services.

**Tech Stack:** Docker Compose (Compose Spec, requires `service_completed_successfully` — Docker Compose v2.17+), Python 3.13, Taskiq, Redis (RedisStreamBroker), PostgreSQL 16.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `ops/docker/Dockerfile` | Modify CMD | Remove shell backgrounding; single `python -m bot` |
| `ops/docker/docker-compose.yml` | Add `migrate`, `worker`, `scheduler` services; update `ratatoskr` and `mobile-api` | Core refactor |
| `ops/docker/docker-compose.dev.yml` | Add volume overrides for new services | Local hot-reload |
| `ops/docker/docker-compose.pi.yml` | Add `worker` Pi override (Qdrant host routing) | Pi deploy |
| `.github/workflows/ci.yml` | Expand `compose-config-check` job | Verify all service commands render |
| `docs/guides/deploy-production.md` | Update stack diagram, health table, singleton note | Docs accuracy |

---

## Task 1: Simplify Dockerfile CMD

**Files:**
- Modify: `ops/docker/Dockerfile`

- [ ] **Step 1: Replace the multi-process shell CMD with a single bot entrypoint**

In `ops/docker/Dockerfile`, lines 121–126 currently read:

```dockerfile
CMD ["sh", "-c", "\
  python -m app.cli.migrate_db && \
  taskiq worker app.tasks.broker:broker app.tasks.digest app.tasks.rss app.tasks.github_sync app.tasks.reconcile_vector_index --workers ${TASKIQ_WORKER_CONCURRENCY:-4} & WORKER_PID=$! ; \
  taskiq scheduler app.tasks.scheduler:scheduler --skip-first-run & SCHED_PID=$! ; \
  python -m bot ; STATUS=$? ; \
  kill $WORKER_PID $SCHED_PID 2>/dev/null ; exit $STATUS"]
```

Replace the entire CMD block with:

```dockerfile
CMD ["python", "-m", "bot"]
```

- [ ] **Step 2: Verify no lingering migrate/taskiq references in the CMD**

```bash
grep -n "CMD\|migrate_db\|taskiq" ops/docker/Dockerfile
```

Expected: only `CMD ["python", "-m", "bot"]` line. No `migrate_db` or `taskiq` lines.

- [ ] **Step 3: Commit**

```bash
git add ops/docker/Dockerfile
git commit -m "refactor(docker): simplify Dockerfile CMD to single bot process"
```

---

## Task 2: Add migrate service and update ratatoskr in docker-compose.yml

**Files:**
- Modify: `ops/docker/docker-compose.yml`

- [ ] **Step 1: Insert the migrate service as the first entry under `services:`**

Insert after `services:` (line 1), before `  ratatoskr:`:

```yaml
  migrate:
    build:
      context: ../..
      dockerfile: ops/docker/Dockerfile
      args:
        VITE_TELEGRAM_BOT_USERNAME: ${VITE_TELEGRAM_BOT_USERNAME:-}
    container_name: ratatoskr-migrate
    init: true
    command: ["python", "-m", "app.cli.migrate_db"]
    env_file:
      - path: ../../.env
        required: false
    environment:
      - DATABASE_URL=${DATABASE_URL:-postgresql+asyncpg://ratatoskr_app:${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}@postgres:5432/ratatoskr}
      - PYTHONUNBUFFERED=1
      - PYTHONDONTWRITEBYTECODE=1
      - RATATOSKR_PROCESS_ROLE=migrate
    volumes:
      - ../../data:/data
      - /etc/localtime:/etc/localtime:ro
    tmpfs:
      - /tmp
    depends_on:
      postgres:
        condition: service_healthy
    restart: "no"
    logging:
      driver: "json-file"
      options:
        max-size: "5m"
        max-file: "2"
    security_opt:
      - no-new-privileges:true
```

- [ ] **Step 2: Update ratatoskr depends_on to include migrate first**

Replace the existing `depends_on:` block of the `ratatoskr` service with:

```yaml
    depends_on:
      migrate:
        condition: service_completed_successfully
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_healthy
      redis:
        condition: service_healthy
      crawl4ai:
        condition: service_healthy
        required: false
      defuddle-api:
        condition: service_healthy
        required: false
```

- [ ] **Step 3: Add RATATOSKR_PROCESS_ROLE=bot explicitly to ratatoskr environment**

In the `ratatoskr` service `environment:` block, add at the end:

```yaml
      - RATATOSKR_PROCESS_ROLE=bot
```

- [ ] **Step 4: Verify compose renders cleanly**

```bash
POSTGRES_PASSWORD=ci-smoke docker compose -f ops/docker/docker-compose.yml config --quiet
```

Expected: exits 0, no errors.

- [ ] **Step 5: Commit**

```bash
git add ops/docker/docker-compose.yml
git commit -m "feat(docker): add migrate one-shot service; ratatoskr waits for migration"
```

---

## Task 3: Add worker service to docker-compose.yml

**Files:**
- Modify: `ops/docker/docker-compose.yml`

- [ ] **Step 1: Insert the worker service after the ratatoskr service block**

Add the following after the closing line of the `ratatoskr` service block (before `  mobile-api:`):

```yaml
  worker:
    build:
      context: ../..
      dockerfile: ops/docker/Dockerfile
      args:
        VITE_TELEGRAM_BOT_USERNAME: ${VITE_TELEGRAM_BOT_USERNAME:-}
    container_name: ratatoskr-worker
    init: true
    command:
      - taskiq
      - worker
      - "app.tasks.broker:broker"
      - app.tasks.digest
      - app.tasks.rss
      - app.tasks.github_sync
      - app.tasks.reconcile_vector_index
      - app.tasks.import_tasks
      - "--workers"
      - "${TASKIQ_WORKER_CONCURRENCY:-4}"
    env_file:
      - path: ../../.env
        required: false
    environment:
      - DATABASE_URL=${DATABASE_URL:-postgresql+asyncpg://ratatoskr_app:${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}@postgres:5432/ratatoskr}
      - QDRANT_URL=http://qdrant:6333
      - REDIS_ENABLED=1
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - TEXTACY_ENABLED=1
      - PYTHONUNBUFFERED=1
      - PYTHONDONTWRITEBYTECODE=1
      - MAX_CONCURRENT_CALLS=${MAX_CONCURRENT_CALLS:-4}
      - REQUEST_TIMEOUT_SEC=${REQUEST_TIMEOUT_SEC:-60}
      - FIRECRAWL_SELF_HOSTED_ENABLED=${FIRECRAWL_SELF_HOSTED_ENABLED:-0}
      - FIRECRAWL_SELF_HOSTED_URL=${FIRECRAWL_SELF_HOSTED_URL:-http://firecrawl-api:3002}
      - SCRAPER_DEFUDDLE_API_BASE_URL=${SCRAPER_DEFUDDLE_API_BASE_URL:-http://defuddle-api:3003}
      - SCRAPER_CRAWL4AI_URL=${SCRAPER_CRAWL4AI_URL:-http://crawl4ai:11235}
      - SCRAPER_DEFUDDLE_TOKEN=${DEFUDDLE_AUTH_TOKEN:-}
      - LLM_PROVIDER=${LLM_PROVIDER:-openrouter}
      - OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-http://localhost:11434/v1}
      - OLLAMA_API_KEY=${OLLAMA_API_KEY:-ollama}
      - OLLAMA_MODEL=${OLLAMA_MODEL:-llama3.3}
      - OTEL_ENABLED=${OTEL_ENABLED:-false}
      - OTEL_EXPORTER_OTLP_ENDPOINT=${OTEL_EXPORTER_OTLP_ENDPOINT:-http://tempo:4317}
      - RATATOSKR_PROCESS_ROLE=worker
    volumes:
      - ../../data:/data
      - /etc/localtime:/etc/localtime:ro
    tmpfs:
      - /tmp
    depends_on:
      migrate:
        condition: service_completed_successfully
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      qdrant:
        condition: service_healthy
      crawl4ai:
        condition: service_healthy
        required: false
      defuddle-api:
        condition: service_healthy
        required: false
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import socket; s=socket.create_connection(('redis', 6379), 5); s.close()"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 30s
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: "0.75"
        reservations:
          memory: 256M
          cpus: "0.25"
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    security_opt:
      - no-new-privileges:true
    stop_grace_period: 60s
```

- [ ] **Step 2: Verify compose renders cleanly**

```bash
POSTGRES_PASSWORD=ci-smoke docker compose -f ops/docker/docker-compose.yml config --quiet
```

Expected: exits 0.

- [ ] **Step 3: Commit**

```bash
git add ops/docker/docker-compose.yml
git commit -m "feat(docker): add dedicated worker service for Taskiq task execution"
```

---

## Task 4: Add scheduler service and update mobile-api in docker-compose.yml

**Files:**
- Modify: `ops/docker/docker-compose.yml`

- [ ] **Step 1: Insert the scheduler service after the worker service block**

Add after the `worker` service closing line (before `  mobile-api:`):

```yaml
  scheduler:
    build:
      context: ../..
      dockerfile: ops/docker/Dockerfile
      args:
        VITE_TELEGRAM_BOT_USERNAME: ${VITE_TELEGRAM_BOT_USERNAME:-}
    container_name: ratatoskr-scheduler
    init: true
    command:
      - taskiq
      - scheduler
      - "app.tasks.scheduler:scheduler"
      - "--skip-first-run"
    env_file:
      - path: ../../.env
        required: false
    environment:
      - DATABASE_URL=${DATABASE_URL:-postgresql+asyncpg://ratatoskr_app:${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}@postgres:5432/ratatoskr}
      - REDIS_ENABLED=1
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - PYTHONUNBUFFERED=1
      - PYTHONDONTWRITEBYTECODE=1
      - DIGEST_ENABLED=${DIGEST_ENABLED:-false}
      - GITHUB_SYNC_ENABLED=${GITHUB_SYNC_ENABLED:-true}
      - GITHUB_SYNC_CRON=${GITHUB_SYNC_CRON:-0 2 * * *}
      - VECTOR_RECONCILE_ENABLED=${VECTOR_RECONCILE_ENABLED:-true}
      - VECTOR_RECONCILE_CRON=${VECTOR_RECONCILE_CRON:-*/30 * * * *}
      - OTEL_ENABLED=${OTEL_ENABLED:-false}
      - OTEL_EXPORTER_OTLP_ENDPOINT=${OTEL_EXPORTER_OTLP_ENDPOINT:-http://tempo:4317}
      - RATATOSKR_PROCESS_ROLE=scheduler
    volumes:
      - /etc/localtime:/etc/localtime:ro
    tmpfs:
      - /tmp
    depends_on:
      migrate:
        condition: service_completed_successfully
      redis:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import socket; s=socket.create_connection(('redis', 6379), 5); s.close()"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 30s
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: "0.20"
        reservations:
          memory: 64M
          cpus: "0.05"
    logging:
      driver: "json-file"
      options:
        max-size: "5m"
        max-file: "2"
    security_opt:
      - no-new-privileges:true
    stop_grace_period: 30s
```

The scheduler is lightweight (reads config, enqueues to Redis — no Qdrant, no data volume, no LLM env). Singleton enforcement is the Compose default (`replicas: 1`); in Swarm deployments add `deploy.mode: replicated` with `replicas: 1` explicitly.

- [ ] **Step 2: Update mobile-api depends_on to include migrate**

In the `mobile-api` service `depends_on:` block, add `migrate` before `postgres:`:

```yaml
    depends_on:
      migrate:
        condition: service_completed_successfully
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_healthy
      redis:
        condition: service_healthy
      crawl4ai:
        condition: service_healthy
        required: false
      defuddle-api:
        condition: service_healthy
        required: false
```

- [ ] **Step 3: Verify all five core services appear**

```bash
POSTGRES_PASSWORD=ci-smoke docker compose -f ops/docker/docker-compose.yml config --services | sort
```

Expected lines include: `migrate`, `mobile-api`, `ratatoskr`, `scheduler`, `worker` (plus infra services).

- [ ] **Step 4: Verify compose renders cleanly**

```bash
POSTGRES_PASSWORD=ci-smoke docker compose -f ops/docker/docker-compose.yml config --quiet
```

Expected: exits 0.

- [ ] **Step 5: Commit**

```bash
git add ops/docker/docker-compose.yml
git commit -m "feat(docker): add isolated scheduler service; mobile-api waits for migration"
```

---

## Task 5: Update docker-compose.dev.yml

**Files:**
- Modify: `ops/docker/docker-compose.dev.yml`

- [ ] **Step 1: Add volume bind-mount overrides for worker, scheduler, and migrate**

Append the following service blocks to the existing `services:` section (after the `mobile-api:` block):

```yaml
  worker:
    volumes:
      - ../../app:/app/app:ro
      - ../../bot.py:/app/bot.py:ro
      - ../../alembic.ini:/app/alembic.ini:ro
      - ../../config:/app/config:ro

  scheduler:
    volumes:
      - ../../app:/app/app:ro
      - ../../alembic.ini:/app/alembic.ini:ro
      - ../../config:/app/config:ro

  migrate:
    volumes:
      - ../../app:/app/app:ro
      - ../../alembic.ini:/app/alembic.ini:ro
      - ../../config:/app/config:ro
```

- [ ] **Step 2: Verify dev overlay renders cleanly**

```bash
POSTGRES_PASSWORD=ci-smoke docker compose \
  -f ops/docker/docker-compose.yml \
  -f ops/docker/docker-compose.dev.yml \
  config --quiet
```

Expected: exits 0.

- [ ] **Step 3: Commit**

```bash
git add ops/docker/docker-compose.dev.yml
git commit -m "feat(docker): add dev overlay volume mounts for worker, scheduler, migrate"
```

---

## Task 6: Update docker-compose.pi.yml

**Files:**
- Modify: `ops/docker/docker-compose.pi.yml`

- [ ] **Step 1: Add Pi override for the worker service**

The worker runs `reconcile_vector_index` which calls Qdrant. On the Pi, Qdrant runs as a native systemd service on the host, not as a Docker container. Add the `worker` entry to the Pi overlay's `services:` section:

```yaml
  worker:
    environment:
      - QDRANT_URL=http://host-gateway:6333
    extra_hosts:
      - "host-gateway:host-gateway"
    networks:
      default: {}
      firecrawl_internal: {}
    depends_on:
      qdrant:
        condition: service_started
        required: false
```

The scheduler and migrate services require no Pi-specific overrides (no Qdrant access, no Firecrawl network).

- [ ] **Step 2: Verify Pi overlay renders cleanly**

```bash
POSTGRES_PASSWORD=ci-smoke docker compose \
  -f ops/docker/docker-compose.yml \
  -f ops/docker/docker-compose.pi.yml \
  config --quiet
```

Expected: exits 0.

- [ ] **Step 3: Commit**

```bash
git add ops/docker/docker-compose.pi.yml
git commit -m "feat(docker): add Pi overlay entry for worker service (Qdrant host routing)"
```

---

## Task 7: Expand CI compose smoke test

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Locate the compose-config-check job**

Find the job starting at approximately line 597:

```yaml
  compose-config-check:
    name: Docker Compose - Config smoke test
    ...
      - name: Validate production compose renders cleanly
        env:
          POSTGRES_PASSWORD: ci-smoke
        run: docker compose -f ops/docker/docker-compose.yml config --quiet
```

- [ ] **Step 2: Replace the single-step job body with expanded checks**

Keep the existing `Checkout` step and replace (or add after) the validation step with:

```yaml
      - name: Validate production compose renders cleanly
        env:
          POSTGRES_PASSWORD: ci-smoke
        run: docker compose -f ops/docker/docker-compose.yml config --quiet

      - name: Verify core service commands are present
        env:
          POSTGRES_PASSWORD: ci-smoke
        run: |
          config=$(docker compose -f ops/docker/docker-compose.yml config)
          for svc_cmd in \
            "python -m bot" \
            "python -m app.cli.migrate_db" \
            "taskiq worker" \
            "taskiq scheduler"; do
            echo "$config" | grep -q "$svc_cmd" \
              || { echo "MISSING command: $svc_cmd"; exit 1; }
          done
          echo "All expected service commands found."

      - name: Verify all core services are listed
        env:
          POSTGRES_PASSWORD: ci-smoke
        run: |
          services=$(docker compose -f ops/docker/docker-compose.yml config --services)
          for svc in migrate ratatoskr worker scheduler mobile-api; do
            echo "$services" | grep -q "^${svc}$" \
              || { echo "MISSING service: $svc"; exit 1; }
          done
          echo "All core services present."

      - name: Validate dev overlay renders cleanly
        env:
          POSTGRES_PASSWORD: ci-smoke
        run: |
          docker compose \
            -f ops/docker/docker-compose.yml \
            -f ops/docker/docker-compose.dev.yml \
            config --quiet
```

- [ ] **Step 3: Verify the workflow YAML is syntactically valid**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" && echo "YAML valid"
```

Expected: `YAML valid`

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: expand compose smoke test to verify all service commands and names"
```

---

## Task 8: Update deployment docs

**Files:**
- Modify: `docs/guides/deploy-production.md`

- [ ] **Step 1: Replace the stack diagram (around line 132) with the new 7-role version**

Find the fenced YAML block under "The production `ops/docker/docker-compose.yml` defines a 5-service stack:" and replace it with:

```yaml
services:
  migrate:              # One-shot migration job — exits 0 before app services start
    command: ["python", "-m", "app.cli.migrate_db"]
    restart: "no"
    depends_on: [postgres]

  ratatoskr:            # Telegram bot
    command: ["python", "-m", "bot"]
    depends_on: [migrate, redis, qdrant (optional)]
    healthcheck: DB ping (asyncpg) every 30s

  worker:               # Taskiq task executor (consumes jobs from Redis)
    command: ["taskiq", "worker", "app.tasks.broker:broker", ...]
    depends_on: [migrate, postgres, redis, qdrant (optional)]
    healthcheck: Redis TCP :6379 every 30s

  scheduler:            # Taskiq task enqueuer — singleton, emits cron jobs
    command: ["taskiq", "scheduler", "app.tasks.scheduler:scheduler", "--skip-first-run"]
    depends_on: [migrate, redis]
    healthcheck: Redis TCP :6379 every 30s

  mobile-api:           # FastAPI REST API
    build: {context: ../.., dockerfile: ops/docker/Dockerfile.api}
    ports: ["127.0.0.1:18000:8000"]
    depends_on: [migrate, redis, qdrant (optional)]
    healthcheck: DB ping (asyncpg) every 30s

  redis:                # Taskiq broker, rate limits, distributed locks
    image: redis:7-alpine

  qdrant:               # Vector search
    image: qdrant/qdrant:v1.13.6
```

- [ ] **Step 2: Replace the Health Checks table (around line 336)**

Replace the existing table with:

```markdown
| Service    | Method                          | Interval | Details                                                         |
| ---------- | ------------------------------- | -------- | --------------------------------------------------------------- |
| migrate    | (none — one-shot exits 0/non-0) | —        | `restart: no`; dependants use `condition: service_completed_successfully` |
| ratatoskr  | DB ping via asyncpg             | 30s      | Verifies DB connectivity; 5 retries, 60s start period           |
| worker     | Redis TCP :6379                 | 30s      | Verifies broker reachability; 5 retries, 30s start period       |
| scheduler  | Redis TCP :6379                 | 30s      | Verifies broker reachability; 5 retries, 30s start period       |
| mobile-api | DB ping via asyncpg             | 30s      | Verifies DB ready; 5 retries, 60s start period                  |
| redis      | `redis-cli ping`                | 10s      | Standard Redis liveness; 5 retries                              |
| qdrant     | HTTP `GET /healthz`             | 30s      | Qdrant health endpoint; 3 retries, 60s start period             |
```

- [ ] **Step 3: Add a scheduler singleton callout in the Operations section**

Under the **Operations** heading, add:

```markdown
### Scheduler singleton

The `scheduler` service has `deploy.replicas: 1` (Compose default). Never run two scheduler
instances against the same Redis broker — they each enqueue every task once per tick, resulting
in duplicate job execution. In Docker Swarm, set `deploy.mode: replicated` with `replicas: 1`
explicitly. On the Pi (systemd + Docker Compose), the compose stack already guarantees a single
instance.
```

- [ ] **Step 4: Update the "Rebuild & redeploy" quickstart note**

The existing command `docker compose -f ops/docker/docker-compose.yml up -d --build` already starts all services including the new ones — no command change needed. Add an explanatory sentence near that command:

> The `migrate` service runs automatically before `ratatoskr`, `worker`, `scheduler`, and `mobile-api` start. There is no need to run migrations manually.

- [ ] **Step 5: Commit**

```bash
git add docs/guides/deploy-production.md
git commit -m "docs: update deploy guide for multi-service architecture (bot/worker/scheduler/migrate)"
```

---

## Self-Review

**Spec coverage:**

| Requirement | Task |
|---|---|
| Remove shell backgrounding of Taskiq worker/scheduler inside bot container | Task 1 |
| Create distinct services: bot, worker, scheduler, migration job | Tasks 2–4 |
| Only one scheduler runs per deployment | Task 4 (singleton note + Compose replicas default) |
| Each service has own command, healthcheck, restart policy, RATATOSKR_PROCESS_ROLE | Tasks 2–4 |
| Remove shell background process management from Dockerfile CMD | Task 1 |
| Update deployment docs and local quickstart | Task 8 |
| Add CI compose smoke test verifying all service commands render | Task 7 |

**Acceptance criteria:**

| Criterion | How satisfied |
|---|---|
| Worker crash does not leave a "healthy" bot container masking the failure | Separate services, independent healthchecks — each has its own liveness signal |
| Scheduler is isolated and singleton | Dedicated `scheduler` service, Compose `replicas: 1` default |
| Migrations run explicitly before app roles start | `migrate` service with `condition: service_completed_successfully` on all app services |

**Notes:**
- `app.tasks.import_tasks` is confirmed present (`git status` shows it as a new untracked file) and is included in the `worker` command list in Task 3.
- `condition: service_completed_successfully` requires Docker Compose v2.17+ (released Nov 2022). All modern Docker Desktop and Linux Docker installs meet this.
- The Pi overlay (`docker-compose.pi.yml`) only needs a `worker` entry — scheduler and migrate have no Qdrant or Firecrawl dependencies.
