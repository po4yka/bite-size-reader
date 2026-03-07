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
# Bot needs: ml, youtube, export, scheduler, mcp (but NOT api)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cache/pip \
    echo "Starting uv sync with extras: ml youtube export scheduler mcp" && \
    uv sync --frozen --no-dev --extra ml --extra youtube --extra export --extra scheduler --extra mcp --verbose && \
    echo "uv sync completed successfully"

# =============================================================================
# Stage 2: Frontend - Build React Mini App
# =============================================================================
FROM node:25-alpine AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
# Output: /app/app/static/digest/

# =============================================================================
# Stage 2.1: Web - Build Carbon Web App
# =============================================================================
FROM node:25-alpine AS web-builder

WORKDIR /app/web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build
# Output: /app/app/static/web/

# =============================================================================
# Stage 2.5: Rust - Build migration runtime binaries
# =============================================================================
FROM rust:slim AS rust-builder

WORKDIR /app/rust

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       pkg-config \
       libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY rust/Cargo.toml rust/Cargo.lock ./
COPY rust/crates ./crates

RUN cargo build --release --locked \
    -p bsr-summary-contract \
    -p bsr-pipeline-shadow \
    -p bsr-interface-router \
    -p bsr-telegram-runtime

# =============================================================================
# Stage 3: Runtime - Minimal production image
# =============================================================================
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:/app/rust/target/release:$PATH" \
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
RUN set -eux; \
    playwright install --with-deps chromium

# Copy application code
COPY app ./app
COPY bot.py ./

# Copy Rust migration binaries into auto-discovery path used by Python bridges
RUN mkdir -p /app/rust/target/release
COPY --from=rust-builder /app/rust/target/release/bsr-summary-contract /app/rust/target/release/bsr-summary-contract
COPY --from=rust-builder /app/rust/target/release/bsr-pipeline-shadow /app/rust/target/release/bsr-pipeline-shadow
COPY --from=rust-builder /app/rust/target/release/bsr-interface-router /app/rust/target/release/bsr-interface-router
COPY --from=rust-builder /app/rust/target/release/bsr-telegram-runtime /app/rust/target/release/bsr-telegram-runtime

# Copy built frontend assets from frontend-builder stage
COPY --from=frontend-builder /app/app/static/digest /app/app/static/digest
# Copy built Carbon web assets
COPY --from=web-builder /app/app/static/web /app/app/static/web

# Create non-root user for security
RUN useradd -r -u 1000 -m -d /home/appuser -s /sbin/nologin appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data

# Runtime configuration
VOLUME ["/data"]
ENV DB_PATH=/data/app.db \
    LOG_LEVEL=INFO \
    REQUEST_TIMEOUT_SEC=60 \
    TEXTACY_ENABLED=1

# Switch to non-root user
USER appuser

# Health check to ensure database is accessible
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import sqlite3, os; \
    conn = sqlite3.connect(os.getenv('DB_PATH', '/data/app.db'), timeout=5); \
    conn.execute('SELECT 1').fetchone(); \
    conn.close()"

# Default command
CMD ["python", "-m", "bot"]
