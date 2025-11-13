# syntax=docker/dockerfile:1

FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
# System deps for building native wheels (e.g., spaCy deps, tgcrypto)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
        gcc \
        libxml2-dev \
        libxslt1-dev \
        zlib1g-dev \
        sqlite3 \
        libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv and sync project dependencies
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen

# Copy application code
COPY app ./app
COPY bot.py ./

# Runtime configuration
VOLUME ["/data"]
ENV DB_PATH=/data/app.db \
    LOG_LEVEL=INFO \
    REQUEST_TIMEOUT_SEC=60 \
    TEXTACY_ENABLED=1

# Default command
CMD ["uv", "run", "bot.py"]
