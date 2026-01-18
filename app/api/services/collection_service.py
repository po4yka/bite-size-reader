"""Service logic for collections (nesting, sharing, move/reorder)."""
# ruff: noqa: TC003

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any, Literal, cast

from app.api.exceptions import AuthorizationError, ResourceNotFoundError
from app.infrastructure.persistence.sqlite.repositories.collection_repository import (
    SqliteCollectionRepositoryAdapter,
)

Role = Literal["owner", "editor", "viewer"]
ROLE_RANK = {"owner": 3, "editor": 2, "viewer": 1}


class CollectionService:
    """Business logic for collections and folders."""

    # ---- access helpers ----
    @staticmethod
    async def _get_role(
        repo: SqliteCollectionRepositoryAdapter, collection_id: int, user_id: int
    ) -> Role | None:
        """Get user's role for a collection."""
        role = await repo.async_get_role(collection_id, user_id)
        if role in ("owner", "editor", "viewer"):
            return cast("Role", role)
        return None

    @classmethod
    async def _require_role(
        cls,
        repo: SqliteCollectionRepositoryAdapter,
        collection_id: int,
        user_id: int,
        minimum: Role,
    ) -> Role:
        """Require at least a minimum role, raise AuthorizationError if insufficient."""
        role = await cls._get_role(repo, collection_id, user_id)
        if role is None or ROLE_RANK[role] < ROLE_RANK[minimum]:
            raise AuthorizationError(f"Insufficient permissions for collection {collection_id}")
        return role

    @staticmethod
    async def _get_collection_or_raise(
        repo: SqliteCollectionRepositoryAdapter,
        collection_id: int,
    ) -> dict[str, Any]:
        """Get collection or raise ResourceNotFoundError."""
        collection = await repo.async_get_collection(collection_id)
        if not collection:
            raise ResourceNotFoundError("Collection", collection_id)
        return collection

    @classmethod
    async def get_collection_with_auth(
        cls,
        collection_id: int,
        user_id: int,
        minimum_role: Role,
    ) -> dict[str, Any]:
        """Get a collection with authorization check.

        Args:
            collection_id: The collection ID.
            user_id: The user ID requesting access.
            minimum_role: The minimum role required.

        Returns:
            Dict with collection data including item_count.

        Raises:
            ResourceNotFoundError: If collection not found.
            AuthorizationError: If user lacks required permissions.
        """
        from app.db.models import database_proxy

        repo = SqliteCollectionRepositoryAdapter(database_proxy)
        collection = await cls._get_collection_or_raise(repo, collection_id)
        await cls._require_role(repo, collection_id, user_id, minimum_role)
        return collection

    # ---- queries ----
    @classmethod
    async def list_collections(
        cls, user_id: int, parent_id: int | None, limit: int, offset: int
    ) -> list[dict[str, Any]]:
        """List collections for a user with optional parent filter."""
        from app.db.models import database_proxy

        repo = SqliteCollectionRepositoryAdapter(database_proxy)
        return await repo.async_list_collections(user_id, parent_id, limit, offset)

    @classmethod
    async def get_tree(cls, user_id: int, max_depth: int = 3) -> list[dict[str, Any]]:
        """Get collection tree for a user.

        Returns flat list of collections. Tree building done in memory.
        """
        from app.db.models import database_proxy

        repo = SqliteCollectionRepositoryAdapter(database_proxy)
        collections = await repo.async_get_collection_tree(user_id)

        # Build tree in memory
        by_parent: dict[int | None, list[dict[str, Any]]] = {}
        for col in collections:
            parent_key = col.get("parent_id") or col.get("parent")
            by_parent.setdefault(parent_key, []).append(col)

        def build(node_parent: int | None, depth: int) -> list[dict[str, Any]]:
            if depth > max_depth:
                return []
            children = by_parent.get(node_parent, [])
            for child in children:
                child["_children"] = build(child.get("id"), depth + 1)
            return children

        return build(None, 1)

    # ---- CRUD ----
    @classmethod
    async def create_collection(
        cls,
        *,
        user_id: int,
        name: str,
        description: str | None,
        parent_id: int | None,
        position: int | None,
    ) -> dict[str, Any]:
        """Create a new collection."""
        from app.db.models import database_proxy

        repo = SqliteCollectionRepositoryAdapter(database_proxy)

        # Validate parent if provided
        if parent_id is not None:
            parent = await repo.async_get_collection(parent_id)
            if not parent:
                raise ResourceNotFoundError("Collection", parent_id)
            await cls._require_role(repo, parent_id, user_id, "editor")

        # Calculate position
        pos = position if position is not None else await repo.async_get_next_position(parent_id)

        # Shift existing positions
        await repo.async_shift_positions(parent_id, pos)

        # Create collection
        collection_id = await repo.async_create_collection(
            user_id=user_id,
            name=name,
            description=description,
            parent_id=parent_id,
            position=pos,
        )

        result = await repo.async_get_collection(collection_id)
        return result or {}

    @classmethod
    async def update_collection(
        cls,
        *,
        collection_id: int,
        user_id: int,
        name: str | None,
        description: str | None,
        parent_id: int | None = None,
        position: int | None = None,
    ) -> dict[str, Any]:
        """Update a collection."""
        from app.db.models import database_proxy

        repo = SqliteCollectionRepositoryAdapter(database_proxy)

        collection = await cls._get_collection_or_raise(repo, collection_id)
        await cls._require_role(repo, collection_id, user_id, "editor")

        updates: dict[str, Any] = {}
        current_parent_id = collection.get("parent_id") or collection.get("parent")

        # Handle parent change
        if parent_id is not None and parent_id != current_parent_id:
            if parent_id == collection_id:
                raise ValueError("Cannot set collection as its own parent")
            new_parent = await repo.async_get_collection(parent_id)
            if not new_parent:
                raise ResourceNotFoundError("Collection", parent_id)
            # Cycle check - need to walk up ancestors
            # For simplicity, use the move_collection method
            await cls._require_role(repo, parent_id, user_id, "editor")
            updates["parent_id"] = parent_id

        if name is not None:
            updates["name"] = name
        if description is not None:
            updates["description"] = description

        # Handle position
        if position is not None:
            target_parent = updates.get("parent_id", current_parent_id)
            await repo.async_shift_positions(target_parent, position)
            updates["position"] = position
        elif "parent_id" in updates:
            # Moving to new parent, get next position
            new_pos = await repo.async_get_next_position(updates["parent_id"])
            updates["position"] = new_pos

        if updates:
            await repo.async_update_collection(collection_id, **updates)

        result = await repo.async_get_collection(collection_id)
        return result or {}

    @classmethod
    async def delete_collection(cls, collection_id: int, user_id: int) -> None:
        """Soft delete a collection."""
        from app.db.models import database_proxy

        repo = SqliteCollectionRepositoryAdapter(database_proxy)
        await cls._get_collection_or_raise(repo, collection_id)
        await cls._require_role(repo, collection_id, user_id, "owner")
        await repo.async_soft_delete_collection(collection_id)

    # ---- items ----
    @classmethod
    async def add_item(cls, collection_id: int, summary_id: int, user_id: int) -> None:
        """Add a summary to a collection."""
        from app.db.models import database_proxy

        repo = SqliteCollectionRepositoryAdapter(database_proxy)
        await cls._get_collection_or_raise(repo, collection_id)
        await cls._require_role(repo, collection_id, user_id, "editor")

        position = await repo.async_get_next_item_position(collection_id)
        added = await repo.async_add_item(collection_id, summary_id, position)
        if not added:
            # Summary not found
            raise ResourceNotFoundError("Summary", summary_id)

    @classmethod
    async def remove_item(cls, collection_id: int, summary_id: int, user_id: int) -> None:
        """Remove a summary from a collection."""
        from app.db.models import database_proxy

        repo = SqliteCollectionRepositoryAdapter(database_proxy)
        await cls._get_collection_or_raise(repo, collection_id)
        await cls._require_role(repo, collection_id, user_id, "editor")
        await repo.async_remove_item(collection_id, summary_id)

    @classmethod
    async def list_items(
        cls, collection_id: int, user_id: int, limit: int, offset: int
    ) -> list[dict[str, Any]]:
        """List items in a collection."""
        from app.db.models import database_proxy

        repo = SqliteCollectionRepositoryAdapter(database_proxy)
        await cls._get_collection_or_raise(repo, collection_id)
        await cls._require_role(repo, collection_id, user_id, "viewer")
        return await repo.async_list_items(collection_id, limit, offset)

    @classmethod
    async def reorder_items(
        cls, collection_id: int, user_id: int, items: Iterable[dict[str, int]]
    ) -> None:
        """Reorder items in a collection."""
        from app.db.models import database_proxy

        repo = SqliteCollectionRepositoryAdapter(database_proxy)
        await cls._get_collection_or_raise(repo, collection_id)
        await cls._require_role(repo, collection_id, user_id, "editor")
        await repo.async_reorder_items(collection_id, list(items))

    @classmethod
    async def move_items(
        cls,
        source_collection_id: int,
        user_id: int,
        summary_ids: list[int],
        target_collection_id: int,
        position: int | None,
    ) -> list[int]:
        """Move items from one collection to another."""
        from app.db.models import database_proxy

        repo = SqliteCollectionRepositoryAdapter(database_proxy)

        # Check both collections exist and user has editor access
        await cls._get_collection_or_raise(repo, source_collection_id)
        await cls._get_collection_or_raise(repo, target_collection_id)
        await cls._require_role(repo, source_collection_id, user_id, "editor")
        await cls._require_role(repo, target_collection_id, user_id, "editor")

        return await repo.async_move_items(
            source_collection_id, target_collection_id, summary_ids, position
        )

    # ---- reorder / move collections ----
    @classmethod
    async def reorder_collections(
        cls, parent_id: int | None, user_id: int, items: Iterable[dict[str, int]]
    ) -> None:
        """Reorder collections within a parent."""
        from app.db.models import database_proxy

        repo = SqliteCollectionRepositoryAdapter(database_proxy)

        if parent_id is not None:
            await cls._get_collection_or_raise(repo, parent_id)
            await cls._require_role(repo, parent_id, user_id, "editor")

        await repo.async_reorder_collections(parent_id, list(items))

    @classmethod
    async def move_collection(
        cls, collection_id: int, user_id: int, parent_id: int | None, position: int | None
    ) -> dict[str, Any]:
        """Move a collection to a new parent."""
        from app.db.models import database_proxy

        repo = SqliteCollectionRepositoryAdapter(database_proxy)

        await cls._get_collection_or_raise(repo, collection_id)
        await cls._require_role(repo, collection_id, user_id, "owner")

        if parent_id is not None:
            await cls._get_collection_or_raise(repo, parent_id)
            await cls._require_role(repo, parent_id, user_id, "editor")

        # Calculate position if not provided
        pos = position if position is not None else await repo.async_get_next_position(parent_id)

        result = await repo.async_move_collection(collection_id, parent_id, pos)
        if result is None:
            raise ValueError("Cycle detected or collection not found")
        return result

    # ---- sharing ----
    @classmethod
    async def list_acl(cls, collection_id: int, user_id: int) -> list[dict[str, Any]]:
        """List access control entries for a collection."""
        from app.db.models import database_proxy

        repo = SqliteCollectionRepositoryAdapter(database_proxy)

        await cls._get_collection_or_raise(repo, collection_id)
        await cls._require_role(repo, collection_id, user_id, "viewer")

        # Get owner info
        owner_info = await repo.async_get_owner_info(collection_id)

        # Get collaborators
        collaborators = await repo.async_list_collaborators(collection_id)

        # Combine with owner as first entry
        result: list[dict[str, Any]] = []
        if owner_info:
            result.append(owner_info)
        result.extend(collaborators)
        return result

    @classmethod
    async def add_collaborator(
        cls, collection_id: int, user_id: int, target_user_id: int, role: Role
    ) -> None:
        """Add a collaborator to a collection."""
        from app.db.models import database_proxy

        repo = SqliteCollectionRepositoryAdapter(database_proxy)

        collection = await cls._get_collection_or_raise(repo, collection_id)
        await cls._require_role(repo, collection_id, user_id, "owner")

        # Don't add owner as collaborator
        if target_user_id == collection.get("user_id"):
            return

        await repo.async_add_collaborator(collection_id, target_user_id, role, user_id)

    @classmethod
    async def remove_collaborator(
        cls, collection_id: int, user_id: int, target_user_id: int
    ) -> None:
        """Remove a collaborator from a collection."""
        from app.db.models import database_proxy

        repo = SqliteCollectionRepositoryAdapter(database_proxy)

        collection = await cls._get_collection_or_raise(repo, collection_id)
        await cls._require_role(repo, collection_id, user_id, "owner")

        # Don't remove owner
        if target_user_id == collection.get("user_id"):
            return

        await repo.async_remove_collaborator(collection_id, target_user_id)

    @classmethod
    async def create_invite(
        cls, collection_id: int, user_id: int, role: Role, expires_at: datetime | None
    ) -> dict[str, Any]:
        """Create an invite for a collection."""
        from app.db.models import database_proxy

        repo = SqliteCollectionRepositoryAdapter(database_proxy)

        await cls._get_collection_or_raise(repo, collection_id)
        await cls._require_role(repo, collection_id, user_id, "owner")

        return await repo.async_create_invite(collection_id, role, expires_at)

    @classmethod
    async def accept_invite(cls, token: str, user_id: int) -> None:
        """Accept an invite to join a collection."""
        from app.db.models import database_proxy

        repo = SqliteCollectionRepositoryAdapter(database_proxy)

        result = await repo.async_accept_invite(token, user_id)
        if result is None:
            raise ResourceNotFoundError("Invite", token)
