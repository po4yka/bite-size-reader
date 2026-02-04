"""
FastAPI application for Bite-Size Reader Mobile API.

Usage:
    uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime

import peewee
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError as PydanticValidationError

from app.api.dependencies import search_resources
from app.api.error_handlers import (
    api_exception_handler,
    database_exception_handler,
    global_exception_handler as global_error_handler,
    validation_exception_handler,
)
from app.api.exceptions import APIException
from app.api.middleware import correlation_id_middleware, rate_limit_middleware
from app.api.models.responses import success_response
from app.api.routers import (
    auth,
    collections,
    health,
    notifications,
    proxy,
    requests,
    search,
    summaries,
    sync,
    system,
    user,
)
from app.config import Config, DatabaseConfig
from app.core.logging_utils import get_logger
from app.core.time_utils import UTC
from app.db.session import DatabaseSessionManager
from app.infrastructure.redis import close_redis

logger = get_logger(__name__)
_db: DatabaseSessionManager | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        yield
    finally:
        await search_resources.shutdown_chroma_search_resources()
        await close_redis()
        if _db:
            _db.database.close()
            logger.info("database_closed")


# FastAPI app instance
app = FastAPI(
    title="Bite-Size Reader Mobile API",
    description="RESTful API for Android/iOS mobile clients",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS configuration
ALLOWED_ORIGINS = Config.get("ALLOWED_ORIGINS", "").split(",")
# Clean up empty strings and whitespace
ALLOWED_ORIGINS = [origin.strip() for origin in ALLOWED_ORIGINS if origin.strip()]

# Default to localhost only if not configured (development mode)
if not ALLOWED_ORIGINS:
    logger.warning(
        "ALLOWED_ORIGINS not configured - defaulting to localhost only. "
        "Set ALLOWED_ORIGINS environment variable for production."
    )
    ALLOWED_ORIGINS = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8080",
    ]
else:
    logger.info(f"CORS allowed origins: {ALLOWED_ORIGINS}")

# CORS middleware with specific origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # Only specific origins
    allow_credentials=True,
    allow_methods=[
        "GET",
        "POST",
        "PATCH",
        "DELETE",
        "OPTIONS",
        "HEAD",
    ],  # Explicit methods
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Correlation-ID",
    ],  # Specific headers
    max_age=3600,  # Cache preflight for 1 hour
)

# Custom middleware
app.middleware("http")(correlation_id_middleware)
app.middleware("http")(rate_limit_middleware)

# Include routers
app.include_router(auth.router, prefix="/v1/auth", tags=["Authentication"])
app.include_router(collections.router, prefix="/v1/collections", tags=["Collections"])
app.include_router(summaries.router, prefix="/v1/summaries", tags=["Summaries"])
app.include_router(summaries.router, prefix="/v1/articles", tags=["Articles"])
app.include_router(requests.router, prefix="/v1/requests", tags=["Requests"])
app.include_router(search.router, prefix="/v1", tags=["Search"])
app.include_router(sync.router, prefix="/v1/sync", tags=["Sync"])
app.include_router(user.router, prefix="/v1/user", tags=["User"])
app.include_router(system.router, prefix="/v1/system", tags=["System"])
app.include_router(proxy.router, prefix="/v1/proxy", tags=["Proxy"])
app.include_router(notifications.router, prefix="/v1/notifications", tags=["Notifications"])
app.include_router(health.router, tags=["Health"])


@app.get("/")
async def root(request: Request):
    """API root endpoint."""
    return success_response(
        {
            "service": "Bite-Size Reader Mobile API",
            "version": app.version,
            "docs": "/docs",
            "health": "/health",
        },
        correlation_id=getattr(request.state, "correlation_id", None),
    )


@app.get("/health")
async def health_check(request: Request):
    """Health check endpoint."""
    return success_response(
        {
            "status": "healthy",
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        },
        correlation_id=getattr(request.state, "correlation_id", None),
    )


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint.

    Returns metrics in Prometheus text format for scraping.
    """
    from fastapi.responses import Response

    from app.observability.metrics import get_metrics, get_metrics_content_type

    return Response(
        content=get_metrics(),
        media_type=get_metrics_content_type(),
    )


# Register exception handlers
app.add_exception_handler(APIException, api_exception_handler)
app.add_exception_handler(
    PydanticValidationError,
    validation_exception_handler,
)
app.add_exception_handler(peewee.DatabaseError, database_exception_handler)
app.add_exception_handler(peewee.OperationalError, database_exception_handler)
app.add_exception_handler(Exception, global_error_handler)


# Initialize database proxy eagerly so Peewee models can be used immediately
DB_PATH = Config.get("DB_PATH", "/data/app.db")
# Pydantic handles type coercion from string env vars
# Pydantic handles string-to-number coercion at runtime via validation_alias
_db_env_overrides: dict[str, str] = {
    key: value
    for key, value in {
        "DB_OPERATION_TIMEOUT": os.getenv("DB_OPERATION_TIMEOUT"),
        "DB_MAX_RETRIES": os.getenv("DB_MAX_RETRIES"),
        "DB_JSON_MAX_SIZE": os.getenv("DB_JSON_MAX_SIZE"),
        "DB_JSON_MAX_DEPTH": os.getenv("DB_JSON_MAX_DEPTH"),
        "DB_JSON_MAX_ARRAY_LENGTH": os.getenv("DB_JSON_MAX_ARRAY_LENGTH"),
        "DB_JSON_MAX_DICT_KEYS": os.getenv("DB_JSON_MAX_DICT_KEYS"),
    }.items()
    if value not in (None, "")
}
db_cfg = DatabaseConfig.model_validate(_db_env_overrides)
_db = DatabaseSessionManager(
    path=DB_PATH,
    operation_timeout=db_cfg.operation_timeout,
    max_retries=db_cfg.max_retries,
    json_max_size=db_cfg.json_max_size,
    json_max_depth=db_cfg.json_max_depth,
    json_max_array_length=db_cfg.json_max_array_length,
    json_max_dict_keys=db_cfg.json_max_dict_keys,
)
_db.database.connect(reuse_if_open=True)
logger.info(
    "database_initialized",
    extra={"db_path": DB_PATH},
)


if __name__ == "__main__":
    import uvicorn

    # Development server - bind to all interfaces for Docker/container access
    uvicorn.run(
        "app.api.main:app",
        # nosec B104 - intentional for development/Docker environments
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
