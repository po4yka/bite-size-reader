"""Collection membership adapter used by automation rules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import Collection, CollectionItem

if TYPE_CHECKING:
    from app.db.session import Database


class SqliteCollectionMembershipAdapter:
    """Add and remove summaries from collections with ownership checks."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def async_add_summary(
        self,
        *,
        user_id: int,
        collection_id: int,
        summary_id: int,
    ) -> str:
        async with self._database.transaction() as session:
            collection = await session.scalar(
                select(Collection.id).where(
                    Collection.id == collection_id,
                    Collection.user_id == user_id,
                    Collection.is_deleted.is_(False),
                )
            )
            if collection is None:
                return f"collection {collection_id} not found or not owned by user"
            inserted_id = await session.scalar(
                insert(CollectionItem)
                .values(collection_id=collection_id, summary_id=summary_id)
                .on_conflict_do_nothing(
                    index_elements=[CollectionItem.collection_id, CollectionItem.summary_id]
                )
                .returning(CollectionItem.id)
            )
            if inserted_id is None:
                return f"already in collection {collection_id}"
            return f"added to collection {collection_id}"

    async def async_remove_summary(
        self,
        *,
        user_id: int,
        collection_id: int,
        summary_id: int,
    ) -> str:
        async with self._database.transaction() as session:
            collection = await session.scalar(
                select(Collection.id).where(
                    Collection.id == collection_id,
                    Collection.user_id == user_id,
                    Collection.is_deleted.is_(False),
                )
            )
            if collection is None:
                return f"collection {collection_id} not found or not owned by user"
            deleted_id = await session.scalar(
                delete(CollectionItem)
                .where(
                    CollectionItem.collection_id == collection_id,
                    CollectionItem.summary_id == summary_id,
                )
                .returning(CollectionItem.id)
            )
            if deleted_id is not None:
                return f"removed from collection {collection_id}"
            return "not in collection"
