"""Item operations for the SQLite collection repository."""

from __future__ import annotations

from typing import Any

from peewee import IntegrityError

from app.db.models import CollectionItem, Summary, model_to_dict

from ._collection_repo_shared import _get_active_collection, _now, logger
from ._repository_mixin_base import SqliteRepositoryMixinBase


class CollectionRepositoryItemsMixin(SqliteRepositoryMixinBase):
    """Collection item CRUD and reordering operations."""

    async def async_get_item_count(self, collection_id: int) -> int:
        """Get the number of items in a collection."""

        def _count() -> int:
            return CollectionItem.select().where(CollectionItem.collection == collection_id).count()

        return await self._execute(_count, operation_name="get_item_count", read_only=True)

    async def async_add_item(
        self,
        collection_id: int,
        summary_id: int,
        position: int,
    ) -> bool:
        """Add a summary to a collection."""

        def _add() -> bool:
            collection = _get_active_collection(collection_id)
            if not collection:
                return False
            summary = Summary.get_or_none(Summary.id == summary_id)
            if not summary:
                return False
            try:
                CollectionItem.create(
                    collection=collection,
                    summary=summary,
                    position=position,
                    created_at=_now(),
                )
                collection.updated_at = _now()
                collection.save()
                return True
            except IntegrityError:
                return False

        return await self._execute(_add, operation_name="add_collection_item")

    async def async_remove_item(self, collection_id: int, summary_id: int) -> None:
        """Remove a summary from a collection."""

        def _remove() -> None:
            collection = _get_active_collection(collection_id)
            if not collection:
                return
            CollectionItem.delete().where(
                (CollectionItem.collection == collection) & (CollectionItem.summary == summary_id)
            ).execute()
            collection.updated_at = _now()
            collection.save()

        await self._execute(_remove, operation_name="remove_collection_item")

    async def async_list_items(
        self,
        collection_id: int,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        """List items in a collection."""

        def _list() -> list[dict[str, Any]]:
            items = (
                CollectionItem.select()
                .where(CollectionItem.collection == collection_id)
                .order_by(CollectionItem.position, CollectionItem.created_at)
                .limit(limit)
                .offset(offset)
            )
            return [model_to_dict(item) or {} for item in items]

        return await self._execute(_list, operation_name="list_collection_items", read_only=True)

    async def async_get_next_item_position(self, collection_id: int) -> int:
        """Get the next position for an item in a collection."""

        def _get() -> int:
            last = (
                CollectionItem.select(CollectionItem.position)
                .where(CollectionItem.collection == collection_id)
                .order_by(CollectionItem.position.desc())
                .first()
            )
            if not last or last.position is None:
                return 1
            return last.position + 1

        return await self._execute(_get, operation_name="get_next_item_position", read_only=True)

    async def async_shift_item_positions(self, collection_id: int, start: int) -> None:
        """Shift item positions in a collection starting at a position."""

        def _shift() -> None:
            CollectionItem.update(position=CollectionItem.position + 1).where(
                (CollectionItem.collection == collection_id)
                & (CollectionItem.position.is_null(False))
                & (CollectionItem.position >= start)
            ).execute()

        await self._execute(_shift, operation_name="shift_item_positions")

    async def async_reorder_items(
        self, collection_id: int, item_positions: list[dict[str, int]]
    ) -> None:
        """Reorder items in a collection."""

        def _reorder() -> None:
            collection = _get_active_collection(collection_id)
            if not collection:
                return
            summary_ids = [item["summary_id"] for item in item_positions]
            existing = {
                row.summary_id
                for row in CollectionItem.select(CollectionItem.summary_id).where(
                    (CollectionItem.collection == collection)
                    & (CollectionItem.summary_id.in_(summary_ids))
                )
            }
            with self._session.database.atomic():
                for item in item_positions:
                    if item["summary_id"] in existing:
                        CollectionItem.update(position=item["position"]).where(
                            (CollectionItem.collection == collection)
                            & (CollectionItem.summary_id == item["summary_id"])
                        ).execute()
                collection.updated_at = _now()
                collection.save()

        await self._execute(_reorder, operation_name="reorder_collection_items")

    async def async_bulk_set_items(self, collection_id: int, summary_ids: list[int]) -> int:
        """Replace all items in a collection atomically."""

        def _bulk_set() -> int:
            collection = _get_active_collection(collection_id)
            if not collection:
                return 0

            with self._session.database.atomic():
                CollectionItem.delete().where(CollectionItem.collection == collection).execute()

                now = _now()
                inserted = 0
                for position, summary_id in enumerate(summary_ids, start=1):
                    summary = Summary.get_or_none(Summary.id == summary_id)
                    if not summary:
                        continue
                    try:
                        CollectionItem.create(
                            collection=collection,
                            summary=summary,
                            position=position,
                            created_at=now,
                        )
                        inserted += 1
                    except IntegrityError:
                        logger.debug(
                            "bulk_set_item_skipped",
                            extra={"summary_id": summary_id, "collection_id": collection_id},
                        )
                        continue

                collection.updated_at = now
                collection.save()

            return inserted

        return await self._execute(_bulk_set, operation_name="bulk_set_collection_items")

    async def async_move_items(
        self,
        source_collection_id: int,
        target_collection_id: int,
        summary_ids: list[int],
        position: int | None,
    ) -> list[int]:
        """Move items from one collection to another."""

        def _move() -> list[int]:
            source = _get_active_collection(source_collection_id)
            target = _get_active_collection(target_collection_id)
            if not source or not target:
                return []

            moved: list[int] = []
            insert_pos = position
            if insert_pos is None:
                last = (
                    CollectionItem.select(CollectionItem.position)
                    .where(CollectionItem.collection == target)
                    .order_by(CollectionItem.position.desc())
                    .first()
                )
                insert_pos = 1 if not last or last.position is None else last.position + 1

            for summary_id in summary_ids:
                CollectionItem.delete().where(
                    (CollectionItem.collection == source)
                    & (CollectionItem.summary_id == summary_id)
                ).execute()
                if position is not None:
                    CollectionItem.update(position=CollectionItem.position + 1).where(
                        (CollectionItem.collection == target)
                        & (CollectionItem.position.is_null(False))
                        & (CollectionItem.position >= insert_pos)
                    ).execute()
                try:
                    CollectionItem.create(
                        collection=target,
                        summary=summary_id,
                        position=insert_pos,
                        created_at=_now(),
                    )
                    moved.append(summary_id)
                    insert_pos += 1
                except IntegrityError:
                    logger.debug(
                        "collection_move_item_skipped",
                        extra={"summary_id": summary_id, "target_collection_id": target.id},
                    )
                    continue

            source.updated_at = _now()
            source.save()
            target.updated_at = _now()
            target.save()
            return moved

        return await self._execute(_move, operation_name="move_collection_items")
