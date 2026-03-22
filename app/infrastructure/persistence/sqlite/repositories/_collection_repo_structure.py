"""Structure and tree operations for the SQLite collection repository."""

from __future__ import annotations

from typing import Any

from app.db.models import Collection, CollectionCollaborator, model_to_dict

from ._collection_repo_shared import _get_active_collection, _now, _serialize_collection
from ._repository_mixin_base import SqliteRepositoryMixinBase


class CollectionRepositoryStructureMixin(SqliteRepositoryMixinBase):
    """Collection CRUD, tree, and reordering operations."""

    async def async_get_collection(
        self, collection_id: int, *, include_deleted: bool = False
    ) -> dict[str, Any] | None:
        """Get a collection by ID."""

        def _get() -> dict[str, Any] | None:
            if include_deleted:
                record = Collection.select().where(Collection.id == collection_id).first()
            else:
                record = _get_active_collection(collection_id)
            if not record:
                return None
            return _serialize_collection(record)

        return await self._execute(_get, operation_name="get_collection", read_only=True)

    async def async_list_collections(
        self,
        user_id: int,
        parent_id: int | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        """List collections for a user with optional parent filter."""

        def _list() -> list[dict[str, Any]]:
            query = (
                Collection.select()
                .where(
                    (~Collection.is_deleted)
                    & (Collection.user_id == user_id)
                    & (
                        (Collection.parent == parent_id)
                        if parent_id is not None
                        else (Collection.parent.is_null(True))
                    )
                )
                .order_by(Collection.position, Collection.created_at)
                .limit(limit)
                .offset(offset)
            )
            return [_serialize_collection(collection) for collection in query]

        return await self._execute(_list, operation_name="list_collections", read_only=True)

    async def async_create_collection(
        self,
        *,
        user_id: int,
        name: str,
        description: str | None,
        parent_id: int | None,
        position: int,
        collection_type: str = "manual",
        query_conditions_json: list[dict] | None = None,
        query_match_mode: str = "all",
    ) -> int:
        """Create a new collection."""

        def _create() -> int:
            parent = _get_active_collection(parent_id) if parent_id is not None else None
            record = Collection.create(
                user_id=user_id,
                name=name,
                description=description,
                parent=parent,
                position=position,
                collection_type=collection_type,
                query_conditions_json=query_conditions_json,
                query_match_mode=query_match_mode,
                created_at=_now(),
                updated_at=_now(),
            )
            return record.id

        return await self._execute(_create, operation_name="create_collection")

    async def async_update_collection(
        self,
        collection_id: int,
        **fields: Any,
    ) -> None:
        """Update a collection by ID."""

        def _update() -> None:
            record = _get_active_collection(collection_id)
            if not record:
                return
            for key, value in fields.items():
                if hasattr(record, key):
                    setattr(record, key, value)
            record.updated_at = _now()
            record.save()

        await self._execute(_update, operation_name="update_collection")

    async def async_soft_delete_collection(self, collection_id: int) -> None:
        """Soft delete a collection."""

        def _delete() -> None:
            record = _get_active_collection(collection_id)
            if not record:
                return
            record.is_deleted = True
            record.deleted_at = _now()
            record.save()

        await self._execute(_delete, operation_name="soft_delete_collection")

    async def async_get_next_position(self, parent_id: int | None) -> int:
        """Get the next position value for a collection in a parent."""

        def _get() -> int:
            last = (
                Collection.select(Collection.position)
                .where((Collection.parent == parent_id) & (~Collection.is_deleted))
                .order_by(Collection.position.desc())
                .first()
            )
            if not last or last.position is None:
                return 1
            return last.position + 1

        return await self._execute(
            _get, operation_name="get_next_collection_position", read_only=True
        )

    async def async_shift_positions(self, parent_id: int | None, start: int) -> None:
        """Shift positions of collections in a parent starting at a position."""

        def _shift() -> None:
            Collection.update(position=Collection.position + 1).where(
                (Collection.parent == parent_id)
                & (Collection.position.is_null(False))
                & (Collection.position >= start)
            ).execute()

        await self._execute(_shift, operation_name="shift_collection_positions")

    async def async_get_collection_tree(self, user_id: int) -> list[dict[str, Any]]:
        """Get all accessible collections for a user."""

        def _get_tree() -> list[dict[str, Any]]:
            collab_ids = CollectionCollaborator.select(CollectionCollaborator.collection_id).where(
                (CollectionCollaborator.user == user_id)
                & (CollectionCollaborator.status == "active")
            )
            collections = (
                Collection.select()
                .where(
                    (~Collection.is_deleted)
                    & ((Collection.user_id == user_id) | (Collection.id.in_(collab_ids)))
                )
                .order_by(Collection.parent, Collection.position, Collection.created_at)
            )
            return [_serialize_collection(collection) for collection in collections]

        return await self._execute(_get_tree, operation_name="get_collection_tree", read_only=True)

    async def async_reorder_collections(
        self,
        parent_id: int | None,
        item_positions: list[dict[str, int]],
    ) -> None:
        """Reorder collections within a parent."""

        def _reorder() -> None:
            collection_ids = [item["collection_id"] for item in item_positions]
            existing = {
                collection.id
                for collection in Collection.select(Collection.id).where(
                    (Collection.id.in_(collection_ids))
                    & (~Collection.is_deleted)
                    & (
                        (Collection.parent == parent_id)
                        if parent_id is not None
                        else (Collection.parent.is_null(True))
                    )
                )
            }
            with self._session.database.atomic():
                for item in item_positions:
                    if item["collection_id"] in existing:
                        Collection.update(position=item["position"]).where(
                            Collection.id == item["collection_id"]
                        ).execute()

        await self._execute(_reorder, operation_name="reorder_collections")

    async def async_move_collection(
        self,
        collection_id: int,
        parent_id: int | None,
        position: int,
    ) -> dict[str, Any] | None:
        """Move a collection to a new parent."""

        def _move() -> dict[str, Any] | None:
            collection = _get_active_collection(collection_id)
            if not collection:
                return None

            new_parent = None
            if parent_id is not None:
                new_parent = _get_active_collection(parent_id)
                if not new_parent:
                    return None
                ancestor = new_parent
                while ancestor:
                    if ancestor.id == collection.id:
                        return None
                    ancestor = ancestor.parent

            Collection.update(position=Collection.position + 1).where(
                (Collection.parent == parent_id)
                & (Collection.position.is_null(False))
                & (Collection.position >= position)
            ).execute()

            collection.parent = new_parent
            collection.position = position
            collection.updated_at = _now()
            collection.save()
            return model_to_dict(collection)

        return await self._execute(_move, operation_name="move_collection")
