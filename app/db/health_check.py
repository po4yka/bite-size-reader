"""Database health check system.

Monitors database performance, integrity, and resource usage.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TYPE_CHECKING


from app.db.models import LLMCall, Request, Summary

if TYPE_CHECKING:
    import peewee

logger = logging.getLogger(__name__)


@dataclass
class HealthCheckResult:
    """Result of a database health check."""

    healthy: bool
    status: str  # "healthy", "degraded", "critical"
    checks: dict[str, dict[str, Any]]
    overall_score: float  # 0.0 - 1.0
    timestamp: float
    errors: list[str]


class DatabaseHealthCheck:
    """Performs comprehensive database health checks."""

    def __init__(self, database: peewee.Database, db_path: str):
        """Initialize health check system.

        Args:
            database: Peewee database instance
            db_path: Path to SQLite database file
        """
        self.database = database
        self.db_path = db_path

    def run_health_check(self) -> HealthCheckResult:
        """Run all health checks and return comprehensive results.

        Returns:
            HealthCheckResult with status and detailed check results
        """
        timestamp = time.time()
        checks: dict[str, dict[str, Any]] = {}
        errors: list[str] = []

        # Run individual checks
        checks["connectivity"] = self._check_connectivity()
        checks["foreign_keys"] = self._check_foreign_keys()
        checks["indexes"] = self._check_indexes()
        checks["disk_space"] = self._check_disk_space()
        checks["query_performance"] = self._check_query_performance()
        checks["data_integrity"] = self._check_data_integrity()
        checks["wal_mode"] = self._check_wal_mode()

        # Collect errors
        for check_name, check_result in checks.items():
            if not check_result.get("healthy", True):
                error_msg = check_result.get("error", f"{check_name} check failed")
                errors.append(error_msg)

        # Calculate overall score
        healthy_checks = sum(1 for check in checks.values() if check.get("healthy", False))
        total_checks = len(checks)
        overall_score = healthy_checks / total_checks if total_checks > 0 else 0.0

        # Determine overall status
        if overall_score >= 0.9:
            status = "healthy"
            healthy = True
        elif overall_score >= 0.6:
            status = "degraded"
            healthy = False
        else:
            status = "critical"
            healthy = False

        return HealthCheckResult(
            healthy=healthy,
            status=status,
            checks=checks,
            overall_score=overall_score,
            timestamp=timestamp,
            errors=errors,
        )

    def _check_connectivity(self) -> dict[str, Any]:
        """Check basic database connectivity."""
        try:
            with self.database.connection_context():
                cursor = self.database.execute_sql("SELECT 1")
                result = cursor.fetchone()

            return {
                "healthy": result is not None and result[0] == 1,
                "message": "Database connection successful",
            }
        except Exception as e:
            logger.error("db_health_connectivity_failed", extra={"error": str(e)})
            return {
                "healthy": False,
                "error": f"Connection failed: {e}",
            }

    def _check_foreign_keys(self) -> dict[str, Any]:
        """Check that foreign key constraints are enabled."""
        try:
            with self.database.connection_context():
                cursor = self.database.execute_sql("PRAGMA foreign_keys")
                result = cursor.fetchone()

            enabled = result is not None and result[0] == 1
            return {
                "healthy": enabled,
                "message": "Foreign keys enabled" if enabled else "Foreign keys DISABLED",
                "enabled": enabled,
            }
        except Exception as e:
            logger.error("db_health_foreign_keys_failed", extra={"error": str(e)})
            return {
                "healthy": False,
                "error": f"Foreign key check failed: {e}",
            }

    def _check_indexes(self) -> dict[str, Any]:
        """Check that expected indexes exist."""
        try:
            expected_indexes = {
                "requests": ["idx_requests_correlation_id", "idx_requests_user_created"],
                "summaries": ["idx_summaries_read_status"],
                "llm_calls": ["idx_llm_calls_request"],
            }

            missing_indexes = []
            for table, expected in expected_indexes.items():
                try:
                    indexes = self.database.get_indexes(table)
                    index_names = {idx.name for idx in indexes}

                    for idx_name in expected:
                        if idx_name not in index_names:
                            missing_indexes.append(f"{table}.{idx_name}")
                except Exception:
                    # Table might not exist
                    pass

            healthy = len(missing_indexes) == 0
            return {
                "healthy": healthy,
                "message": "All critical indexes exist" if healthy else "Missing indexes",
                "missing_indexes": missing_indexes,
            }
        except Exception as e:
            logger.error("db_health_indexes_failed", extra={"error": str(e)})
            return {
                "healthy": False,
                "error": f"Index check failed: {e}",
            }

    def _check_disk_space(self) -> dict[str, Any]:
        """Check database file size and available disk space."""
        try:
            if self.db_path == ":memory:":
                return {
                    "healthy": True,
                    "message": "In-memory database, no disk usage",
                }

            db_file = Path(self.db_path)
            if not db_file.exists():
                return {
                    "healthy": False,
                    "error": "Database file does not exist",
                }

            # Get database file size
            db_size_bytes = db_file.stat().st_size
            db_size_mb = db_size_bytes / (1024 * 1024)

            # Get available disk space
            import shutil

            stat = shutil.disk_usage(db_file.parent)
            free_space_mb = stat.free / (1024 * 1024)

            # Warn if less than 100MB free
            healthy = free_space_mb > 100

            return {
                "healthy": healthy,
                "message": f"DB: {db_size_mb:.1f}MB, Free: {free_space_mb:.1f}MB",
                "db_size_mb": round(db_size_mb, 2),
                "free_space_mb": round(free_space_mb, 2),
            }
        except Exception as e:
            logger.error("db_health_disk_space_failed", extra={"error": str(e)})
            return {
                "healthy": False,
                "error": f"Disk space check failed: {e}",
            }

    def _check_query_performance(self) -> dict[str, Any]:
        """Check query performance with simple benchmark."""
        try:
            # Benchmark: SELECT on indexed column
            start = time.time()
            with self.database.connection_context():
                Request.select().where(Request.correlation_id == "nonexistent").first()
            indexed_query_ms = (time.time() - start) * 1000

            # Benchmark: Simple count
            start = time.time()
            with self.database.connection_context():
                Request.select().count()
            count_query_ms = (time.time() - start) * 1000

            # Healthy if queries complete within reasonable time
            healthy = indexed_query_ms < 100 and count_query_ms < 500

            return {
                "healthy": healthy,
                "message": f"Indexed: {indexed_query_ms:.1f}ms, Count: {count_query_ms:.1f}ms",
                "indexed_query_ms": round(indexed_query_ms, 2),
                "count_query_ms": round(count_query_ms, 2),
            }
        except Exception as e:
            logger.error("db_health_query_performance_failed", extra={"error": str(e)})
            return {
                "healthy": False,
                "error": f"Query performance check failed: {e}",
            }

    def _check_data_integrity(self) -> dict[str, Any]:
        """Check for data integrity issues."""
        try:
            issues = []

            # Check for orphaned LLM calls (should be impossible with NOT NULL + CASCADE)
            with self.database.connection_context():
                orphaned_llm_count = LLMCall.select().where(LLMCall.request.is_null()).count()

            if orphaned_llm_count > 0:
                issues.append(f"{orphaned_llm_count} orphaned LLM calls")

            # Check for summaries without requests (should be impossible)
            with self.database.connection_context():
                orphaned_summary_count = Summary.select().where(Summary.request.is_null()).count()

            if orphaned_summary_count > 0:
                issues.append(f"{orphaned_summary_count} orphaned summaries")

            healthy = len(issues) == 0
            return {
                "healthy": healthy,
                "message": "No integrity issues" if healthy else "Integrity issues found",
                "issues": issues,
            }
        except Exception as e:
            logger.error("db_health_data_integrity_failed", extra={"error": str(e)})
            return {
                "healthy": False,
                "error": f"Data integrity check failed: {e}",
            }

    def _check_wal_mode(self) -> dict[str, Any]:
        """Check that WAL mode is enabled for better concurrency."""
        try:
            with self.database.connection_context():
                cursor = self.database.execute_sql("PRAGMA journal_mode")
                result = cursor.fetchone()

            mode = result[0] if result else "unknown"
            healthy = mode.lower() == "wal"

            return {
                "healthy": healthy,
                "message": f"Journal mode: {mode}",
                "journal_mode": mode,
            }
        except Exception as e:
            logger.error("db_health_wal_mode_failed", extra={"error": str(e)})
            return {
                "healthy": False,
                "error": f"WAL mode check failed: {e}",
            }

    def get_database_stats(self) -> dict[str, Any]:
        """Get comprehensive database statistics.

        Returns:
            Dictionary with table counts, sizes, and other metrics
        """
        stats: dict[str, Any] = {}

        try:
            with self.database.connection_context():
                # Table counts
                stats["requests"] = Request.select().count()
                stats["summaries"] = Summary.select().count()
                stats["llm_calls"] = LLMCall.select().count()

                # Database file size
                if self.db_path != ":memory:":
                    db_file = Path(self.db_path)
                    if db_file.exists():
                        stats["db_size_mb"] = round(db_file.stat().st_size / (1024 * 1024), 2)

        except Exception as e:
            logger.error("db_stats_failed", extra={"error": str(e)})
            stats["error"] = str(e)

        return stats
