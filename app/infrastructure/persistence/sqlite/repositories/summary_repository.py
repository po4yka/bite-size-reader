"""Thin compatibility shell for the SQLite summary repository adapter."""

from __future__ import annotations

from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository

from ._summary_repo_reads import SummaryRepositoryReadMixin
from ._summary_repo_state import SummaryRepositoryStateMixin
from ._summary_repo_sync import SummaryRepositorySyncMixin
from ._summary_repo_writes import SummaryRepositoryWriteMixin


class SqliteSummaryRepositoryAdapter(
    SummaryRepositoryWriteMixin,
    SummaryRepositoryReadMixin,
    SummaryRepositoryStateMixin,
    SummaryRepositorySyncMixin,
    SqliteBaseRepository,
):
    """Compatibility assembly for the public summary repository adapter."""
