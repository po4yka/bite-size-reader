"""SQLite implementation of collection repository.

This adapter handles Collection, CollectionItem, CollectionCollaborator,
and CollectionInvite operations.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from peewee import IntegrityError

from app.core.time_utils import UTC
from app.db.models import (
    Collection,
    CollectionCollaborator,
    CollectionInvite,
    CollectionItem,
    Summary,
    model_to_dict,
)
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository


def _now() -> dt.datetime:
    """Get current UTC time."""
    return dt.datetime.now(UTC)


class SqliteCollectionRepositoryAdapter(SqliteBaseRepository):
    """Adapter for collection-related operations."""

    # -------------------------------------------------------------------------
    # Collection CRUD
    # -------------------------------------------------------------------------

    async def async_get_collection(
        self, collection_id: int, *, include_deleted: bool = False
    ) -> dict[str, Any] | None:
        """Get a collection by ID.

        Returns:
            Dict with collection data including item_count, or None if not found.
        """

        def _get() -> dict[str, Any] | None:
            query = Collection.select().where(Collection.id == collection_id)
            if not include_deleted:
                query = query.where(~Collection.is_deleted)
            record = query.first()
            if not record:
                return None
            data = model_to_dict(record) or {}
            data["item_count"] = (
                CollectionItem.select().where(CollectionItem.collection == record.id).count()
            )
            return data

        return await self._execute(_get, operation_name="get_collection", read_only=True)

    async def async_list_collections(
        self,
        user_id: int,
        parent_id: int | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        """List collections for a user with optional parent filter.

        Returns:
            List of collection dicts with item_count included.
        """

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
            result = []
            for c in query:
                data = model_to_dict(c) or {}
                data["item_count"] = (
                    CollectionItem.select().where(CollectionItem.collection == c.id).count()
                )
                result.append(data)
            return result

        return await self._execute(_list, operation_name="list_collections", read_only=True)

    async def async_get_item_count(self, collection_id: int) -> int:
        """Get the number of items in a collection.

        Args:
            collection_id: The collection ID.

        Returns:
            Number of items in the collection.
        """

        def _count() -> int:
            return CollectionItem.select().where(CollectionItem.collection == collection_id).count()

        return await self._execute(_count, operation_name="get_item_count", read_only=True)

    async def async_create_collection(
        self,
        *,
        user_id: int,
        name: str,
        description: str | None,
        parent_id: int | None,
        position: int,
    ) -> int:
        """Create a new collection.

        Returns:
            The ID of the created collection.
        """

        def _create() -> int:
            parent = None
            if parent_id is not None:
                parent = Collection.get_or_none(
                    (Collection.id == parent_id) & (~Collection.is_deleted)
                )
            record = Collection.create(
                user_id=user_id,
                name=name,
                description=description,
                parent=parent,
                position=position,
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
            record = Collection.get_or_none(
                (Collection.id == collection_id) & (~Collection.is_deleted)
            )
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
            record = Collection.get_or_none(
                (Collection.id == collection_id) & (~Collection.is_deleted)
            )
            if not record:
                return
            record.is_deleted = True
            record.deleted_at = _now()
            record.save()

        await self._execute(_delete, operation_name="soft_delete_collection")

    async def async_get_next_position(self, parent_id: int | None) -> int:
        """Get the next position value for a collection in a parent.

        Returns:
            Next position integer.
        """

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

    # -------------------------------------------------------------------------
    # CollectionItem Operations
    # -------------------------------------------------------------------------

    async def async_add_item(
        self,
        collection_id: int,
        summary_id: int,
        position: int,
    ) -> bool:
        """Add a summary to a collection.

        Returns:
            True if item was added, False if already exists.
        """

        def _add() -> bool:
            collection = Collection.get_or_none(
                (Collection.id == collection_id) & (~Collection.is_deleted)
            )
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
            collection = Collection.get_or_none(
                (Collection.id == collection_id) & (~Collection.is_deleted)
            )
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
        """List items in a collection.

        Returns:
            List of collection item dicts.
        """

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
        """Get the next position for an item in a collection.

        Returns:
            Next position integer.
        """

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
        """Reorder items in a collection.

        Args:
            collection_id: The collection ID.
            item_positions: List of dicts with 'summary_id' and 'position'.
        """

        def _reorder() -> None:
            collection = Collection.get_or_none(
                (Collection.id == collection_id) & (~Collection.is_deleted)
            )
            if not collection:
                return
            summary_ids = [item["summary_id"] for item in item_positions]
            existing = {
                row.summary_id: row
                for row in CollectionItem.select().where(
                    (CollectionItem.collection == collection)
                    & (CollectionItem.summary_id.in_(summary_ids))
                )
            }
            for item in item_positions:
                row = existing.get(item["summary_id"])
                if row:
                    row.position = item["position"]
                    row.save()
            collection.updated_at = _now()
            collection.save()

        await self._execute(_reorder, operation_name="reorder_collection_items")

    # -------------------------------------------------------------------------
    # CollectionCollaborator Operations
    # -------------------------------------------------------------------------

    async def async_get_role(self, collection_id: int, user_id: int) -> str | None:
        """Get a user's role for a collection.

        Returns:
            Role string ('owner', 'editor', 'viewer') or None.
        """

        def _get() -> str | None:
            collection = Collection.get_or_none(
                (Collection.id == collection_id) & (~Collection.is_deleted)
            )
            if not collection:
                return None
            if collection.user_id == user_id:
                return "owner"
            collab = (
                CollectionCollaborator.select()
                .where(
                    (CollectionCollaborator.collection == collection)
                    & (CollectionCollaborator.user == user_id)
                    & (CollectionCollaborator.status == "active")
                )
                .first()
            )
            return collab.role if collab else None

        return await self._execute(_get, operation_name="get_collection_role", read_only=True)

    async def async_add_collaborator(
        self,
        collection_id: int,
        target_user_id: int,
        role: str,
        invited_by: int | None,
    ) -> None:
        """Add or update a collaborator on a collection."""

        def _add() -> None:
            collection = Collection.get_or_none(
                (Collection.id == collection_id) & (~Collection.is_deleted)
            )
            if not collection:
                return
            if target_user_id == collection.user_id:
                return
            CollectionCollaborator.insert(
                collection=collection,
                user=target_user_id,
                role=role,
                status="active",
                invited_by=invited_by,
                created_at=_now(),
                updated_at=_now(),
            ).on_conflict_replace().execute()
            collection.is_shared = True
            collection.share_count = (
                CollectionCollaborator.select()
                .where(
                    (CollectionCollaborator.collection == collection)
                    & (CollectionCollaborator.status == "active")
                )
                .count()
            )
            collection.save()

        await self._execute(_add, operation_name="add_collaborator")

    async def async_remove_collaborator(self, collection_id: int, target_user_id: int) -> None:
        """Remove a collaborator from a collection."""

        def _remove() -> None:
            collection = Collection.get_or_none(
                (Collection.id == collection_id) & (~Collection.is_deleted)
            )
            if not collection:
                return
            if target_user_id == collection.user_id:
                return
            CollectionCollaborator.delete().where(
                (CollectionCollaborator.collection == collection)
                & (CollectionCollaborator.user == target_user_id)
            ).execute()
            collection.share_count = (
                CollectionCollaborator.select()
                .where(
                    (CollectionCollaborator.collection == collection)
                    & (CollectionCollaborator.status == "active")
                )
                .count()
            )
            collection.is_shared = collection.share_count > 0
            collection.save()

        await self._execute(_remove, operation_name="remove_collaborator")

    async def async_list_collaborators(self, collection_id: int) -> list[dict[str, Any]]:
        """List collaborators for a collection.

        Returns:
            List of collaborator dicts.
        """

        def _list() -> list[dict[str, Any]]:
            collaborators = (
                CollectionCollaborator.select()
                .where(CollectionCollaborator.collection == collection_id)
                .order_by(CollectionCollaborator.created_at)
            )
            return [model_to_dict(c) or {} for c in collaborators]

        return await self._execute(_list, operation_name="list_collaborators", read_only=True)

    # -------------------------------------------------------------------------
    # CollectionInvite Operations
    # -------------------------------------------------------------------------

    async def async_create_invite(
        self,
        collection_id: int,
        role: str,
        expires_at: dt.datetime | None,
    ) -> dict[str, Any]:
        """Create an invite for a collection.

        Returns:
            Dict with invite data including the token.
        """

        def _create() -> dict[str, Any]:
            collection = Collection.get_or_none(
                (Collection.id == collection_id) & (~Collection.is_deleted)
            )
            if not collection:
                return {}
            token = uuid.uuid4().hex
            invite = CollectionInvite.create(
                collection=collection,
                token=token,
                role=role,
                expires_at=expires_at,
                status="active",
                created_at=_now(),
                updated_at=_now(),
            )
            return model_to_dict(invite) or {}

        return await self._execute(_create, operation_name="create_invite")

    async def async_get_invite_by_token(self, token: str) -> dict[str, Any] | None:
        """Get an invite by token.

        Returns:
            Dict with invite data or None if not found.
        """

        def _get() -> dict[str, Any] | None:
            invite = CollectionInvite.get_or_none(CollectionInvite.token == token)
            return model_to_dict(invite)

        return await self._execute(_get, operation_name="get_invite_by_token", read_only=True)

    async def async_update_invite(self, invite_id: int, **fields: Any) -> None:
        """Update an invite by ID."""

        def _update() -> None:
            invite = CollectionInvite.get_or_none(CollectionInvite.id == invite_id)
            if not invite:
                return
            for key, value in fields.items():
                if hasattr(invite, key):
                    setattr(invite, key, value)
            invite.updated_at = _now()
            invite.save()

        await self._execute(_update, operation_name="update_invite")

    # -------------------------------------------------------------------------
    # Tree Queries
    # -------------------------------------------------------------------------

    async def async_get_collection_tree(self, user_id: int) -> list[dict[str, Any]]:
        """Get all accessible collections for a user (for tree building).

        Returns:
            List of all accessible collection dicts with item_count included.
        """

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
            result = []
            for c in collections:
                data = model_to_dict(c) or {}
                data["item_count"] = (
                    CollectionItem.select().where(CollectionItem.collection == c.id).count()
                )
                result.append(data)
            return result

        return await self._execute(_get_tree, operation_name="get_collection_tree", read_only=True)

    # -------------------------------------------------------------------------
    # Advanced Collection Operations
    # -------------------------------------------------------------------------

    async def async_move_items(
        self,
        source_collection_id: int,
        target_collection_id: int,
        summary_ids: list[int],
        position: int | None,
    ) -> list[int]:
        """Move items from one collection to another.

        Args:
            source_collection_id: Source collection ID.
            target_collection_id: Target collection ID.
            summary_ids: List of summary IDs to move.
            position: Starting position in target (None = append).

        Returns:
            List of successfully moved summary IDs.
        """

        def _move() -> list[int]:
            source = Collection.get_or_none(
                (Collection.id == source_collection_id) & (~Collection.is_deleted)
            )
            target = Collection.get_or_none(
                (Collection.id == target_collection_id) & (~Collection.is_deleted)
            )
            if not source or not target:
                return []

            moved: list[int] = []
            # Calculate starting position
            insert_pos = position
            if insert_pos is None:
                last = (
                    CollectionItem.select(CollectionItem.position)
                    .where(CollectionItem.collection == target)
                    .order_by(CollectionItem.position.desc())
                    .first()
                )
                insert_pos = 1 if not last or last.position is None else last.position + 1

            for sid in summary_ids:
                # Remove from source
                CollectionItem.delete().where(
                    (CollectionItem.collection == source) & (CollectionItem.summary_id == sid)
                ).execute()
                # Shift target positions if placing at specific slot
                if position is not None:
                    CollectionItem.update(position=CollectionItem.position + 1).where(
                        (CollectionItem.collection == target)
                        & (CollectionItem.position.is_null(False))
                        & (CollectionItem.position >= insert_pos)
                    ).execute()
                try:
                    CollectionItem.create(
                        collection=target,
                        summary=sid,
                        position=insert_pos,
                        created_at=_now(),
                    )
                    moved.append(sid)
                    insert_pos += 1
                except IntegrityError:
                    continue

            source.updated_at = _now()
            source.save()
            target.updated_at = _now()
            target.save()
            return moved

        return await self._execute(_move, operation_name="move_collection_items")

    async def async_reorder_collections(
        self,
        parent_id: int | None,
        item_positions: list[dict[str, int]],
    ) -> None:
        """Reorder collections within a parent.

        Args:
            parent_id: Parent collection ID (None for root).
            item_positions: List of dicts with 'collection_id' and 'position'.
        """

        def _reorder() -> None:
            ids = [item["collection_id"] for item in item_positions]
            existing = {
                col.id: col
                for col in Collection.select().where(
                    (Collection.id.in_(ids))
                    & (~Collection.is_deleted)
                    & (
                        (Collection.parent == parent_id)
                        if parent_id is not None
                        else (Collection.parent.is_null(True))
                    )
                )
            }
            for item in item_positions:
                col = existing.get(item["collection_id"])
                if col:
                    col.position = item["position"]
                    col.save()

        await self._execute(_reorder, operation_name="reorder_collections")

    async def async_move_collection(
        self,
        collection_id: int,
        parent_id: int | None,
        position: int,
    ) -> dict[str, Any] | None:
        """Move a collection to a new parent.

        Args:
            collection_id: Collection to move.
            parent_id: New parent ID (None for root).
            position: Position in new parent.

        Returns:
            Updated collection dict or None if not found/cycle detected.
        """

        def _move() -> dict[str, Any] | None:
            collection = Collection.get_or_none(
                (Collection.id == collection_id) & (~Collection.is_deleted)
            )
            if not collection:
                return None

            new_parent = None
            if parent_id is not None:
                new_parent = Collection.get_or_none(
                    (Collection.id == parent_id) & (~Collection.is_deleted)
                )
                if not new_parent:
                    return None
                # Check for cycles
                ancestor = new_parent
                while ancestor:
                    if ancestor.id == collection.id:
                        return None  # Cycle detected
                    ancestor = ancestor.parent

            # Shift positions in target parent
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

    async def async_accept_invite(
        self,
        token: str,
        user_id: int,
    ) -> dict[str, Any] | None:
        """Accept an invite and add user as collaborator.

        Args:
            token: Invite token.
            user_id: User accepting the invite.

        Returns:
            Dict with status info or None if invite not found/invalid.
        """

        def _accept() -> dict[str, Any] | None:
            invite = CollectionInvite.get_or_none(CollectionInvite.token == token)
            if not invite:
                return None
            if invite.status in {"used", "revoked"}:
                return None
            if invite.expires_at and invite.expires_at < _now():
                invite.status = "expired"
                invite.save()
                return None

            collection = invite.collection
            if not collection or collection.is_deleted:
                return None

            # Don't add owner as collaborator
            if user_id != collection.user_id:
                CollectionCollaborator.insert(
                    collection=collection,
                    user=user_id,
                    role=invite.role,
                    status="active",
                    invited_by=collection.user_id,
                    created_at=_now(),
                    updated_at=_now(),
                ).on_conflict_replace().execute()

                collection.is_shared = True
                collection.share_count = (
                    CollectionCollaborator.select()
                    .where(
                        (CollectionCollaborator.collection == collection)
                        & (CollectionCollaborator.status == "active")
                    )
                    .count()
                )
                collection.save()

            invite.used_at = _now()
            invite.status = "used"
            invite.updated_at = _now()
            invite.save()

            return {
                "collection_id": collection.id,
                "role": invite.role,
                "status": "accepted",
            }

        return await self._execute(_accept, operation_name="accept_invite")

    async def async_get_owner_info(self, collection_id: int) -> dict[str, Any] | None:
        """Get owner info for a collection (for ACL list).

        Returns:
            Dict with owner user info or None if collection not found.
        """

        def _get() -> dict[str, Any] | None:
            from app.db.models import User

            collection = Collection.get_or_none(
                (Collection.id == collection_id) & (~Collection.is_deleted)
            )
            if not collection:
                return None
            owner = User.get_or_none(User.telegram_user_id == collection.user_id)
            return {
                "collection_id": collection.id,
                "user_id": collection.user_id,
                "owner_user": model_to_dict(owner) if owner else None,
                "role": "owner",
                "status": "active",
            }

        return await self._execute(_get, operation_name="get_collection_owner", read_only=True)
