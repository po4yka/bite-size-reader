"""
FastAPI application for Bite-Size Reader Mobile API.

Usage:
    uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path as _Path

import peewee
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError as PydanticValidationError

from app.api.error_handlers import (
    api_exception_handler,
    database_exception_handler,
    global_exception_handler as global_error_handler,
    validation_exception_handler,
)
from app.api.exceptions import APIException
from app.api.middleware import (
    correlation_id_middleware,
    rate_limit_middleware,
    webapp_auth_middleware,
)
from app.api.models.responses import success_response
from app.api.routers import (
    auth,
    collections,
    custom_digests,
    digest,
    health,
    highlights,
    notifications,
    proxy,
    requests,
    search,
    summaries,
    sync,
    system,
    tts,
    user,
)
from app.api.routers.auth import get_current_user
from app.config import Config
from app.core.logging_utils import get_logger
from app.core.time_utils import UTC
from app.di.api import build_api_runtime, close_api_runtime, set_current_api_runtime
from app.infrastructure.redis import close_redis

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime = None
    try:
        runtime = await build_api_runtime()
        app.state.runtime = runtime
        set_current_api_runtime(runtime)
        logger.info("database_initialized", extra={"db_path": runtime.db.path})
        yield
    finally:
        await close_redis()
        if runtime is not None:
            await close_api_runtime(runtime)
            set_current_api_runtime(None)
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
        "X-Telegram-Init-Data",
    ],  # Specific headers
    max_age=3600,  # Cache preflight for 1 hour
)

# Custom middleware (order: last added = outermost = runs first)
# correlation_id must run first, then auth, then rate limit
app.middleware("http")(rate_limit_middleware)
app.middleware("http")(webapp_auth_middleware)
app.middleware("http")(correlation_id_middleware)

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
app.include_router(digest.router, prefix="/v1/digest", tags=["Digest"])
app.include_router(custom_digests.router, prefix="/v1/digests/custom", tags=["custom-digests"])
app.include_router(highlights.router, prefix="/v1/summaries", tags=["Highlights"])
app.include_router(tts.router, prefix="/v1/summaries", tags=["TTS"])
app.include_router(health.router, tags=["Health"])

# Serve static files (Mini App HTML for session init, etc.)
_static_dir = _Path(__file__).resolve().parent.parent / "static"
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

_web_index = _static_dir / "web" / "index.html"


def _serve_web_index() -> FileResponse:
    if not _web_index.is_file():
        raise HTTPException(status_code=404, detail="Web interface is not built")
    return FileResponse(str(_web_index))


@app.get("/web/privacy.html")
async def privacy_policy():
    """Serve Privacy Policy static page."""
    _privacy = _static_dir / "web" / "privacy.html"
    if not _privacy.is_file():
        raise HTTPException(status_code=404, detail="Privacy policy page not found")
    return FileResponse(str(_privacy))


@app.get("/web/terms.html")
async def terms_of_service():
    """Serve Terms of Service static page."""
    _terms = _static_dir / "web" / "terms.html"
    if not _terms.is_file():
        raise HTTPException(status_code=404, detail="Terms of service page not found")
    return FileResponse(str(_terms))


@app.get("/web")
@app.get("/web/{path:path}")
async def web_interface(path: str = ""):
    """Serve Carbon web SPA entrypoint."""
    del path
    return _serve_web_index()


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
async def metrics(_: dict = Depends(get_current_user)):
    """Prometheus metrics endpoint (owner-only).

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


if __name__ == "__main__":
    import uvicorn

    # Development server - bind to all interfaces for Docker/container access
    uvicorn.run(
        "app.api.main:app",
        host="0.0.0.0",  # nosec B104 - intentional for Docker
        port=8000,
        reload=True,
        log_level="info",
    )
