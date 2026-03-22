"""Thin compatibility shell for the SQLite collection repository adapter."""

from __future__ import annotations

from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository

from ._collection_repo_access import CollectionRepositoryAccessMixin
from ._collection_repo_invites import CollectionRepositoryInviteMixin
from ._collection_repo_items import CollectionRepositoryItemsMixin
from ._collection_repo_smart import CollectionRepositorySmartMixin
from ._collection_repo_structure import CollectionRepositoryStructureMixin


class SqliteCollectionRepositoryAdapter(
    CollectionRepositoryStructureMixin,
    CollectionRepositoryItemsMixin,
    CollectionRepositoryAccessMixin,
    CollectionRepositoryInviteMixin,
    CollectionRepositorySmartMixin,
    SqliteBaseRepository,
):
    """Compatibility assembly for the public collection repository adapter."""
