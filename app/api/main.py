"""
FastAPI application for Bite-Size Reader Mobile API.

Usage:
    uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
from pydantic import ValidationError as PydanticValidationError
import logging
import peewee

from app.config import Config
from app.api.routers import summaries, requests, search, sync, auth, user
from app.api.middleware import correlation_id_middleware, rate_limit_middleware
from app.api.models.responses import ErrorResponse
from app.api.exceptions import APIException
from app.api.error_handlers import (
    api_exception_handler,
    validation_exception_handler,
    database_exception_handler,
    global_exception_handler as global_error_handler,
)
from app.core.logging_utils import get_logger

logger = get_logger(__name__)

# FastAPI app instance
app = FastAPI(
    title="Bite-Size Reader Mobile API",
    description="RESTful API for Android/iOS mobile clients",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
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
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],  # Explicit methods
    allow_headers=["Authorization", "Content-Type", "X-Correlation-ID"],  # Specific headers
    max_age=3600,  # Cache preflight for 1 hour
)

# Custom middleware
app.middleware("http")(correlation_id_middleware)
app.middleware("http")(rate_limit_middleware)

# Include routers
app.include_router(auth.router, prefix="/v1/auth", tags=["Authentication"])
app.include_router(summaries.router, prefix="/v1/summaries", tags=["Summaries"])
app.include_router(requests.router, prefix="/v1/requests", tags=["Requests"])
app.include_router(search.router, prefix="/v1", tags=["Search"])
app.include_router(sync.router, prefix="/v1/sync", tags=["Sync"])
app.include_router(user.router, prefix="/v1/user", tags=["User"])


@app.get("/")
async def root():
    """API root endpoint."""
    return {
        "success": True,
        "data": {
            "service": "Bite-Size Reader Mobile API",
            "version": "1.0.0",
            "docs": "/docs",
            "health": "/health",
        },
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "success": True,
        "data": {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
    }


# Register exception handlers
app.add_exception_handler(APIException, api_exception_handler)
app.add_exception_handler(PydanticValidationError, validation_exception_handler)
app.add_exception_handler(peewee.DatabaseError, database_exception_handler)
app.add_exception_handler(peewee.OperationalError, database_exception_handler)
app.add_exception_handler(Exception, global_error_handler)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
