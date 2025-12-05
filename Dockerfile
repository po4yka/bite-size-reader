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
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cache/pip \
    uv sync --frozen --no-dev

# =============================================================================
# Stage 2: Runtime - Minimal production image
# =============================================================================
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app:$PYTHONPATH"

WORKDIR /app

# Install only runtime dependencies (no build tools)
# ffmpeg is required for yt-dlp video/audio merging
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       sqlite3 \
       libsqlite3-0 \
       libxml2 \
       libxslt1.1 \
       zlib1g \
       ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy virtual environment from builder stage
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY app ./app
COPY bot.py ./

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
