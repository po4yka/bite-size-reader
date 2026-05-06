"""Read-side service for admin API endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.api.dependencies.database import get_session_manager
from app.api.services.system_maintenance_service import SystemMaintenanceService
from app.infrastructure.persistence.sqlite.repositories.admin_read_repository import (
    SqliteAdminReadRepositoryAdapter,
)

if TYPE_CHECKING:
    import datetime as _dt

    from app.db.session import Database


class AdminReadService:
    """Owns admin dashboards and audit log read models."""

    def __init__(self, session_manager: Database | None = None) -> None:
        self._db = session_manager or get_session_manager()
        self._admin_repo = SqliteAdminReadRepositoryAdapter(self._db)

    async def list_users(self) -> dict[str, Any]:
        return await self._admin_repo.async_list_users()

    async def job_status(self, *, today: _dt.datetime) -> dict[str, Any]:
        return await self._admin_repo.async_job_status(today=today)

    async def content_health(self) -> dict[str, Any]:
        return await self._admin_repo.async_content_health()

    async def system_metrics(self, *, since: _dt.datetime) -> dict[str, Any]:
        metrics = await self._admin_repo.async_system_metrics(since=since)
        metrics["database"] = await SystemMaintenanceService(database=self._db).get_db_info()
        return metrics

    async def audit_log(
        self,
        *,
        action: str | None,
        user_id_filter: int | None,
        since: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        return await self._admin_repo.async_audit_log(
            action=action,
            user_id_filter=user_id_filter,
            since=since,
            limit=limit,
            offset=offset,
        )
