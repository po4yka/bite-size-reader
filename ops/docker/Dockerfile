# syntax=docker/dockerfile:1

# =============================================================================
# Stage 1: Builder - Install dependencies and compile wheels
# =============================================================================
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install build dependencies (will not be in final image)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       gcc \
       g++ \
       libxml2-dev \
       libxslt1-dev \
       zlib1g-dev \
       libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies with cache mounts for faster rebuilds
# Bot/MCP need: ml, youtube, export, scheduler, mcp, api (mcp http_auth imports app.api.routers.auth.tokens)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cache/pip \
    echo "Starting uv sync with extras: ml youtube export scheduler mcp api attachment otel" && \
    uv sync --frozen --no-dev --extra ml --extra youtube --extra export --extra scheduler --extra mcp --extra api --extra browser_scraper --extra attachment --extra otel --verbose && \
    echo "uv sync completed successfully"

# =============================================================================
# Stage 2: Web - Build Carbon Web App
# =============================================================================
FROM node:25-alpine AS web-builder

ARG VITE_TELEGRAM_BOT_USERNAME=""
ENV VITE_TELEGRAM_BOT_USERNAME=$VITE_TELEGRAM_BOT_USERNAME

WORKDIR /app/web
COPY clients/web/package*.json clients/web/.npmrc ./
RUN npm ci
COPY clients/web/ ./
RUN npm run build
# Output: /app/static/web/

# =============================================================================
# Stage 3: Runtime - Minimal production image
# =============================================================================
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app:$PYTHONPATH"

WORKDIR /app

# Install only runtime dependencies (no build tools)
# ffmpeg is required for yt-dlp video/audio merging (can be disabled with build-arg)
ARG WITH_FFMPEG=1
RUN set -eux; \
    apt-get update; \
    pkgs="sqlite3 libsqlite3-0 libxml2 libxslt1.1 zlib1g"; \
    if [ "${WITH_FFMPEG}" = "1" ]; then pkgs="$pkgs ffmpeg"; fi; \
    apt-get install -y --no-install-recommends ${pkgs}; \
    rm -rf /var/lib/apt/lists/*; \
    apt-get clean

# Copy virtual environment from builder stage
COPY --from=builder /app/.venv /app/.venv

# Install Chromium for Playwright-based scraping fallback.
# Set WITH_PLAYWRIGHT=0 at build time to produce a slimmer image without
# the browser engine (e.g. when SCRAPER_PLAYWRIGHT_ENABLED=false).
ARG WITH_PLAYWRIGHT=1
RUN set -eux; \
    if [ "${WITH_PLAYWRIGHT}" = "1" ]; then \
        playwright install --with-deps chromium; \
    fi

# Copy application code
COPY app ./app
COPY bot.py ./

# Copy built Carbon web assets
COPY --from=web-builder /app/static/web /app/app/static/web

# Create non-root user for security
RUN useradd -r -u 1000 -m -d /home/appuser -s /sbin/nologin appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data

# Runtime configuration
VOLUME ["/data"]
ENV DB_PATH=/data/ratatoskr.db \
    LOG_LEVEL=INFO \
    REQUEST_TIMEOUT_SEC=60 \
    TEXTACY_ENABLED=1 \
    RATATOSKR_PROCESS_ROLE=bot

# Switch to non-root user
USER appuser

# Health check to ensure database is accessible
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import sqlite3, os; \
    conn = sqlite3.connect(os.getenv('DB_PATH', '/data/ratatoskr.db'), timeout=5); \
    conn.execute('SELECT 1').fetchone(); \
    conn.close()"

# Default command — bot + taskiq worker + taskiq scheduler in one container.
# The scheduler emits tasks; the worker consumes and executes them.
# Only one scheduler instance must run per deployment.
CMD ["sh", "-c", "\
  python -m app.cli.migrate_db \"${DB_PATH:-/data/ratatoskr.db}\" && \
  taskiq worker app.tasks.broker:broker --fs-discover --workers ${TASKIQ_WORKER_CONCURRENCY:-4} & WORKER_PID=$! ; \
  taskiq scheduler app.tasks.scheduler:scheduler --skip-first-run & SCHED_PID=$! ; \
  python -m bot ; STATUS=$? ; \
  kill $WORKER_PID $SCHED_PID 2>/dev/null ; exit $STATUS"]
