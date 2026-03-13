"""Enhanced health check router with comprehensive system status.

Provides detailed health information about:
- Database connectivity and health score
- Redis availability
- Circuit breaker states
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter

from app.api.dependencies.database import get_session_manager
from app.api.models.responses import success_response
from app.config import load_config
from app.core.logging_utils import get_logger
from app.core.time_utils import UTC, format_iso_z

logger = get_logger(__name__)

router = APIRouter()
_DATABASE_DETAILS_TTL_SECONDS = 30.0
_database_details_cache: dict[str, Any] | None = None
_database_details_cached_at = 0.0
_database_details_lock = asyncio.Lock()


def clear_health_check_cache() -> None:
    """Reset cached component details used by health endpoints."""
    global _database_details_cache, _database_details_cached_at
    _database_details_cache = None
    _database_details_cached_at = 0.0


def _compute_database_details() -> dict[str, Any]:
    """Compute heavier database diagnostics using the shared session manager."""
    db = get_session_manager()
    db_conn = db.database

    cursor = db_conn.execute_sql(
        "SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()"
    )
    size_bytes = cursor.fetchone()[0] if cursor else 0
    integrity_ok, integrity_result = db.check_integrity()

    result: dict[str, Any] = {
        "size_bytes": size_bytes,
        "size_mb": round(size_bytes / (1024 * 1024), 2) if size_bytes else 0,
        "integrity_ok": integrity_ok,
    }
    if not integrity_ok:
        result["integrity_detail"] = integrity_result
    return result


async def _get_cached_database_details() -> dict[str, Any]:
    """Return cached database diagnostics, recomputing only when stale."""
    global _database_details_cache, _database_details_cached_at

    now = time.monotonic()
    if (
        _database_details_cache is not None
        and now - _database_details_cached_at < _DATABASE_DETAILS_TTL_SECONDS
    ):
        return dict(_database_details_cache)

    async with _database_details_lock:
        now = time.monotonic()
        if (
            _database_details_cache is not None
            and now - _database_details_cached_at < _DATABASE_DETAILS_TTL_SECONDS
        ):
            return dict(_database_details_cache)

        details = await asyncio.to_thread(_compute_database_details)
        _database_details_cache = details
        _database_details_cached_at = now
        return dict(details)


async def _check_database(*, include_details: bool = True) -> dict[str, Any]:
    """Check database connectivity and health."""
    start = time.perf_counter()
    try:
        db = get_session_manager()
        db_conn = db.database
        cursor = db_conn.execute_sql("SELECT 1")
        cursor.fetchone()
        latency_ms = (time.perf_counter() - start) * 1000

        result: dict[str, Any] = {
            "status": "healthy",
            "latency_ms": round(latency_ms, 2),
        }
        if include_details:
            result.update(await _get_cached_database_details())
        return result
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        logger.debug(
            "health_check_db_failed",
            extra={"error": str(exc), "latency_ms": latency_ms},
        )
        return {
            "status": "unhealthy",
            "error": str(exc),
            "latency_ms": round(latency_ms, 2),
        }


async def _check_redis() -> dict[str, Any]:
    """Check Redis connectivity using shared client."""
    start = time.perf_counter()
    try:
        from app.infrastructure.redis import get_connection_state, get_redis

        config = load_config()
        if not config.redis.enabled:
            return {"status": "disabled", "latency_ms": 0}

        # Get connection state for detailed reporting
        conn_state = get_connection_state()

        redis_client = await get_redis(config)
        latency_ms = (time.perf_counter() - start) * 1000

        if redis_client is None:
            result: dict[str, Any] = {
                "status": "unavailable",
                "latency_ms": round(latency_ms, 2),
            }
            # Add connection state details
            last_attempt = conn_state["last_attempt"]
            last_error = conn_state["last_error"]
            if isinstance(last_attempt, float) and last_attempt > 0:
                result["last_attempt"] = format_iso_z(datetime.fromtimestamp(last_attempt, tz=UTC))
            if isinstance(last_error, str) and last_error:
                result["error"] = last_error
            return result

        ping_result = redis_client.ping()
        if asyncio.iscoroutine(ping_result):
            async with asyncio.timeout(5.0):
                await ping_result
        latency_ms = (time.perf_counter() - start) * 1000
        return {
            "status": "healthy",
            "latency_ms": round(latency_ms, 2),
        }
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        logger.debug(
            "health_check_redis_failed",
            extra={"error": str(exc), "latency_ms": latency_ms},
        )
        return {
            "status": "unhealthy",
            "error": str(exc),
            "latency_ms": round(latency_ms, 2),
        }


async def _check_scraper() -> dict[str, Any]:
    """Return scraper configuration diagnostics."""
    start = time.perf_counter()
    try:
        from app.adapters.content.scraper.diagnostics import build_scraper_diagnostics

        config = load_config()
        diagnostics = build_scraper_diagnostics(config)
        diagnostics["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
        return diagnostics
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        logger.debug(
            "health_check_scraper_failed",
            extra={"error": str(exc), "latency_ms": latency_ms},
        )
        return {
            "status": "unhealthy",
            "error": str(exc),
            "latency_ms": round(latency_ms, 2),
        }


def _get_circuit_breaker_states() -> dict[str, Any]:
    """Get circuit breaker states for all services."""
    states = {}

    # Circuit breaker states would be integrated with actual client instances
    # For now, return placeholder indicating integration is needed
    states["firecrawl"] = {"state": "unknown", "info": "Not integrated"}
    states["openrouter"] = {"state": "unknown", "info": "Not integrated"}

    return states


@router.get("/health/detailed")
async def detailed_health_check():
    """Comprehensive health check with component status.

    Returns detailed status of all system components:
    - Database connectivity and size
    - Redis availability
    - Circuit breaker states
    - Overall health score
    """
    start_time = time.perf_counter()

    # Run component checks concurrently
    try:
        async with asyncio.timeout(10.0):
            db_status, redis_status, scraper_status = await asyncio.gather(
                _check_database(include_details=True),
                _check_redis(),
                _check_scraper(),
                return_exceptions=True,
            )
    except TimeoutError:
        db_status = {"status": "timeout", "error": "Health check timed out"}
        redis_status = {"status": "timeout", "error": "Health check timed out"}
        scraper_status = {"status": "timeout", "error": "Health check timed out"}

    # Handle exceptions from gather
    if isinstance(db_status, BaseException):
        db_status = {"status": "error", "error": str(db_status)}
    if isinstance(redis_status, BaseException):
        redis_status = {"status": "error", "error": str(redis_status)}
    if isinstance(scraper_status, BaseException):
        scraper_status = {"status": "error", "error": str(scraper_status)}

    circuit_breaker_states = _get_circuit_breaker_states()

    # Calculate health score
    health_score = 0.0

    db_healthy = db_status.get("status") == "healthy"
    redis_healthy = redis_status.get("status") in ("healthy", "disabled")

    if db_healthy:
        health_score += 50.0
    if redis_healthy:
        health_score += 50.0

    # Overall status
    overall_status = "healthy"
    if health_score < 100:
        overall_status = "degraded"
    if health_score < 50:
        overall_status = "unhealthy"

    total_latency_ms = (time.perf_counter() - start_time) * 1000

    return success_response(
        data={
            "status": overall_status,
            "health_score": health_score,
            "timestamp": format_iso_z(datetime.now(UTC)),
            "total_latency_ms": round(total_latency_ms, 2),
            "components": {
                "database": db_status,
                "redis": redis_status,
                "scraper": scraper_status,
                "circuit_breakers": circuit_breaker_states,
            },
        }
    )


@router.get("/health/ready")
async def readiness_check():
    """Kubernetes readiness probe.

    Returns 200 if the service is ready to handle requests.
    Checks database connectivity only.
    """
    db_status = await _check_database(include_details=False)

    if db_status.get("status") == "healthy":
        return success_response(
            data={
                "ready": True,
                "timestamp": format_iso_z(datetime.now(UTC)),
            }
        )

    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=503,
        content={
            "ready": False,
            "error": db_status.get("error", "Database not ready"),
            "timestamp": format_iso_z(datetime.now(UTC)),
        },
    )


@router.get("/health/live")
async def liveness_check():
    """Kubernetes liveness probe.

    Returns 200 if the service is running.
    Minimal check - just verifies the process is responsive.
    """
    return success_response(
        data={
            "alive": True,
            "timestamp": format_iso_z(datetime.now(UTC)),
        }
    )
