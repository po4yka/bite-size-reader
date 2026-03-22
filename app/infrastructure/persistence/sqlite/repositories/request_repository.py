"""Thin compatibility shell for the SQLite request repository adapter."""

from __future__ import annotations

from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository

from ._request_repo_reads import RequestRepositoryReadMixin
from ._request_repo_shared import RequestRepositoryMappingMixin
from ._request_repo_telegram import RequestRepositoryTelegramMixin
from ._request_repo_writes import RequestRepositoryWriteMixin


class SqliteRequestRepositoryAdapter(
    RequestRepositoryTelegramMixin,
    RequestRepositoryWriteMixin,
    RequestRepositoryReadMixin,
    RequestRepositoryMappingMixin,
    SqliteBaseRepository,
):
    """Compatibility assembly for the public request repository adapter."""
