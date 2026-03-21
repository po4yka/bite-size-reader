"""Collection membership adapter used by automation rules."""

from __future__ import annotations

import peewee

from app.db.models import Collection, CollectionItem
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository


class SqliteCollectionMembershipAdapter(SqliteBaseRepository):
    """Add and remove summaries from collections with ownership checks."""

    async def async_add_summary(
        self,
        *,
        user_id: int,
        collection_id: int,
        summary_id: int,
    ) -> str:
        def _add() -> str:
            collection = Collection.get_or_none(
                (Collection.id == collection_id)
                & (Collection.user == user_id)
                & (~Collection.is_deleted)
            )
            if collection is None:
                return f"collection {collection_id} not found or not owned by user"
            try:
                CollectionItem.create(collection=collection_id, summary=summary_id)
                return f"added to collection {collection_id}"
            except peewee.IntegrityError:
                return f"already in collection {collection_id}"

        return await self._execute(_add, operation_name="rule_add_collection_item")

    async def async_remove_summary(
        self,
        *,
        user_id: int,
        collection_id: int,
        summary_id: int,
    ) -> str:
        def _remove() -> str:
            collection = Collection.get_or_none(
                (Collection.id == collection_id)
                & (Collection.user == user_id)
                & (~Collection.is_deleted)
            )
            if collection is None:
                return f"collection {collection_id} not found or not owned by user"
            deleted = (
                CollectionItem.delete()
                .where(
                    (CollectionItem.collection == collection_id)
                    & (CollectionItem.summary == summary_id)
                )
                .execute()
            )
            if deleted:
                return f"removed from collection {collection_id}"
            return "not in collection"

        return await self._execute(_remove, operation_name="rule_remove_collection_item")
