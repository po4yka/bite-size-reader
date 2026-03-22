"""Access control operations for the SQLite collection repository."""

from __future__ import annotations

from typing import Any

from app.db.models import CollectionCollaborator, User, model_to_dict

from ._collection_repo_shared import (
    _get_active_collection,
    _now,
    _recompute_share_state,
)
from ._repository_mixin_base import SqliteRepositoryMixinBase


class CollectionRepositoryAccessMixin(SqliteRepositoryMixinBase):
    """Collaborator, ACL, and owner lookup operations."""

    async def async_get_role(self, collection_id: int, user_id: int) -> str | None:
        """Get a user's role for a collection."""

        def _get() -> str | None:
            collection = _get_active_collection(collection_id)
            if not collection:
                return None
            if collection.user_id == user_id:
                return "owner"
            collaborator = (
                CollectionCollaborator.select()
                .where(
                    (CollectionCollaborator.collection == collection)
                    & (CollectionCollaborator.user == user_id)
                    & (CollectionCollaborator.status == "active")
                )
                .first()
            )
            return collaborator.role if collaborator else None

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
            collection = _get_active_collection(collection_id)
            if not collection or target_user_id == collection.user_id:
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
            _recompute_share_state(collection)

        await self._execute(_add, operation_name="add_collaborator")

    async def async_remove_collaborator(self, collection_id: int, target_user_id: int) -> None:
        """Remove a collaborator from a collection."""

        def _remove() -> None:
            collection = _get_active_collection(collection_id)
            if not collection or target_user_id == collection.user_id:
                return
            CollectionCollaborator.delete().where(
                (CollectionCollaborator.collection == collection)
                & (CollectionCollaborator.user == target_user_id)
            ).execute()
            _recompute_share_state(collection)

        await self._execute(_remove, operation_name="remove_collaborator")

    async def async_list_collaborators(self, collection_id: int) -> list[dict[str, Any]]:
        """List collaborators for a collection."""

        def _list() -> list[dict[str, Any]]:
            collaborators = (
                CollectionCollaborator.select()
                .where(CollectionCollaborator.collection == collection_id)
                .order_by(CollectionCollaborator.created_at)
            )
            return [model_to_dict(collaborator) or {} for collaborator in collaborators]

        return await self._execute(_list, operation_name="list_collaborators", read_only=True)

    async def async_get_owner_info(self, collection_id: int) -> dict[str, Any] | None:
        """Get owner info for a collection."""

        def _get() -> dict[str, Any] | None:
            collection = _get_active_collection(collection_id)
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
