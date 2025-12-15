"""Service logic for collections (nesting, sharing, move/reorder)."""
# ruff: noqa: TC003

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Literal

from peewee import IntegrityError

from app.api.exceptions import AuthorizationError, ResourceNotFoundError
from app.core.time_utils import UTC
from app.db.models import (
    Collection,
    CollectionCollaborator,
    CollectionInvite,
    CollectionItem,
    Summary,
    User,
)

Role = Literal["owner", "editor", "viewer"]
ROLE_RANK = {"owner": 3, "editor": 2, "viewer": 1}


class CollectionService:
    """Business logic for collections and folders."""

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    # ---- access helpers ----
    @staticmethod
    def _get_role(collection: Collection, user_id: int) -> Role | None:
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

    @classmethod
    def _require_role(cls, collection: Collection, user_id: int, minimum: Role) -> Role:
        role = cls._get_role(collection, user_id)
        if role is None or ROLE_RANK[role] < ROLE_RANK[minimum]:
            raise AuthorizationError(f"Insufficient permissions for collection {collection.id}")
        return role

    # ---- queries ----
    @classmethod
    def list_collections(
        cls, user_id: int, parent_id: int | None, limit: int, offset: int
    ) -> list[Collection]:
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
        )
        return list(query.limit(limit).offset(offset))

    @classmethod
    def get_tree(cls, user_id: int, max_depth: int = 3) -> list[Collection]:
        # Simple approach: fetch all accessible collections and build tree in memory
        collab_ids = CollectionCollaborator.select(CollectionCollaborator.collection_id).where(
            (CollectionCollaborator.user == user_id) & (CollectionCollaborator.status == "active")
        )
        collections = (
            Collection.select()
            .where(
                (~Collection.is_deleted)
                & ((Collection.user_id == user_id) | (Collection.id.in_(collab_ids)))
            )
            .order_by(Collection.parent, Collection.position, Collection.created_at)
        )
        by_parent: dict[int | None, list[Collection]] = {}
        for col in collections:
            by_parent.setdefault(col.parent_id, []).append(col)

        def build(node_parent: int | None, depth: int) -> list[Collection]:
            if depth > max_depth:
                return []
            children = by_parent.get(node_parent, [])
            for child in children:
                child._children = build(child.id, depth + 1)
            return children

        return build(None, 1)

    # ---- mutating helpers ----
    @staticmethod
    def _next_position(parent_id: int | None) -> int:
        last = (
            Collection.select(Collection.position)
            .where((Collection.parent == parent_id) & (~Collection.is_deleted))
            .order_by(Collection.position.desc())
            .first()
        )
        if not last or last.position is None:
            return 1
        return last.position + 1

    @staticmethod
    def _next_item_position(collection: Collection) -> int:
        last = (
            CollectionItem.select(CollectionItem.position)
            .where(CollectionItem.collection == collection)
            .order_by(CollectionItem.position.desc())
            .first()
        )
        if not last or last.position is None:
            return 1
        return last.position + 1

    @classmethod
    def _shift_positions(cls, parent_id: int | None, start: int) -> None:
        Collection.update(position=Collection.position + 1).where(
            (Collection.parent == parent_id)
            & (Collection.position.is_null(False))
            & (Collection.position >= start)
        ).execute()

    @classmethod
    def _shift_item_positions(cls, collection: Collection, start: int) -> None:
        CollectionItem.update(position=CollectionItem.position + 1).where(
            (CollectionItem.collection == collection)
            & (CollectionItem.position.is_null(False))
            & (CollectionItem.position >= start)
        ).execute()

    # ---- CRUD ----
    @classmethod
    def create_collection(
        cls,
        *,
        user_id: int,
        name: str,
        description: str | None,
        parent_id: int | None,
        position: int | None,
    ) -> Collection:
        parent = None
        if parent_id is not None:
            parent = Collection.get_or_none(Collection.id == parent_id, ~Collection.is_deleted)
            if not parent:
                raise ResourceNotFoundError("Collection", parent_id)
            cls._require_role(parent, user_id, "editor")
        pos = position if position is not None else cls._next_position(parent_id)
        cls._shift_positions(parent_id, pos)
        return Collection.create(
            user_id=user_id,
            name=name,
            description=description,
            parent=parent,
            position=pos,
            created_at=cls._now(),
            updated_at=cls._now(),
        )

    @classmethod
    def update_collection(
        cls,
        *,
        collection_id: int,
        user_id: int,
        name: str | None,
        description: str | None,
        parent_id: int | None = None,
        position: int | None = None,
    ) -> Collection:
        collection = Collection.get_or_none(
            (Collection.id == collection_id) & (~Collection.is_deleted)
        )
        if not collection:
            raise ResourceNotFoundError("Collection", collection_id)
        cls._require_role(collection, user_id, "editor")

        # Parent change
        if parent_id is not None and parent_id != collection.parent_id:
            if parent_id == collection.id:
                raise ValueError("Cannot set collection as its own parent")
            new_parent = Collection.get_or_none(
                (Collection.id == parent_id) & (~Collection.is_deleted)
            )
            if not new_parent:
                raise ResourceNotFoundError("Collection", parent_id)
            # Prevent cycles: ensure new_parent not descendant
            ancestor = new_parent
            while ancestor:
                if ancestor.id == collection.id:
                    raise ValueError("Cycle detected")
                ancestor = ancestor.parent
            cls._require_role(new_parent, user_id, "editor")
            collection.parent = new_parent
            collection.position = None  # recalculated below

        if name is not None:
            collection.name = name
        if description is not None:
            collection.description = description

        # Position handling
        if position is not None:
            target_parent_id = collection.parent_id
            cls._shift_positions(target_parent_id, position)
            collection.position = position
        elif collection.position is None:
            collection.position = cls._next_position(collection.parent_id)

        collection.updated_at = cls._now()
        collection.save()
        return collection

    @classmethod
    def delete_collection(cls, collection_id: int, user_id: int) -> None:
        collection = Collection.get_or_none(
            (Collection.id == collection_id) & (~Collection.is_deleted)
        )
        if not collection:
            raise ResourceNotFoundError("Collection", collection_id)
        cls._require_role(collection, user_id, "owner")
        collection.is_deleted = True
        collection.deleted_at = cls._now()
        collection.save()

    # ---- items ----
    @classmethod
    def add_item(cls, collection_id: int, summary_id: int, user_id: int) -> None:
        collection = Collection.get_or_none(
            (Collection.id == collection_id) & (~Collection.is_deleted)
        )
        if not collection:
            raise ResourceNotFoundError("Collection", collection_id)
        cls._require_role(collection, user_id, "editor")
        summary = Summary.get_or_none(Summary.id == summary_id)
        if not summary:
            raise ResourceNotFoundError("Summary", summary_id)

        try:
            CollectionItem.create(
                collection=collection,
                summary=summary,
                position=cls._next_item_position(collection),
                created_at=cls._now(),
            )
        except IntegrityError:
            # Already exists: no-op
            return
        collection.updated_at = cls._now()
        collection.save()

    @classmethod
    def remove_item(cls, collection_id: int, summary_id: int, user_id: int) -> None:
        collection = Collection.get_or_none(
            (Collection.id == collection_id) & (~Collection.is_deleted)
        )
        if not collection:
            raise ResourceNotFoundError("Collection", collection_id)
        cls._require_role(collection, user_id, "editor")
        CollectionItem.delete().where(
            (CollectionItem.collection == collection) & (CollectionItem.summary == summary_id)
        ).execute()
        collection.updated_at = cls._now()
        collection.save()

    @classmethod
    def list_items(
        cls, collection_id: int, user_id: int, limit: int, offset: int
    ) -> list[CollectionItem]:
        collection = Collection.get_or_none(
            (Collection.id == collection_id) & (~Collection.is_deleted)
        )
        if not collection:
            raise ResourceNotFoundError("Collection", collection_id)
        cls._require_role(collection, user_id, "viewer")
        return list(
            CollectionItem.select()
            .where(CollectionItem.collection == collection)
            .order_by(CollectionItem.position, CollectionItem.created_at)
            .limit(limit)
            .offset(offset)
        )

    @classmethod
    def reorder_items(
        cls, collection_id: int, user_id: int, items: Iterable[dict[str, int]]
    ) -> None:
        collection = Collection.get_or_none(
            (Collection.id == collection_id) & (~Collection.is_deleted)
        )
        if not collection:
            raise ResourceNotFoundError("Collection", collection_id)
        cls._require_role(collection, user_id, "editor")
        summary_ids = [item["summary_id"] for item in items]
        existing = {
            row.summary_id: row
            for row in CollectionItem.select().where(
                (CollectionItem.collection == collection)
                & (CollectionItem.summary_id.in_(summary_ids))
            )
        }
        for item in items:
            row = existing.get(item["summary_id"])
            if not row:
                continue
            row.position = item["position"]
            row.save()
        collection.updated_at = cls._now()
        collection.save()

    @classmethod
    def move_items(
        cls,
        source_collection_id: int,
        user_id: int,
        summary_ids: list[int],
        target_collection_id: int,
        position: int | None,
    ) -> list[int]:
        source = Collection.get_or_none(
            (Collection.id == source_collection_id) & (~Collection.is_deleted)
        )
        target = Collection.get_or_none(
            (Collection.id == target_collection_id) & (~Collection.is_deleted)
        )
        if not source or not target:
            raise ResourceNotFoundError("Collection", target_collection_id)
        cls._require_role(source, user_id, "editor")
        cls._require_role(target, user_id, "editor")

        moved: list[int] = []
        insert_pos = position if position is not None else cls._next_item_position(target)
        for sid in summary_ids:
            # remove from source
            CollectionItem.delete().where(
                (CollectionItem.collection == source) & (CollectionItem.summary_id == sid)
            ).execute()
            # shift target positions if placing at a specific slot
            if position is not None:
                cls._shift_item_positions(target, insert_pos)
            try:
                CollectionItem.create(
                    collection=target,
                    summary=sid,
                    position=insert_pos,
                    created_at=cls._now(),
                )
                moved.append(sid)
                insert_pos += 1
            except IntegrityError:
                continue
        source.updated_at = cls._now()
        source.save()
        target.updated_at = cls._now()
        target.save()
        return moved

    # ---- reorder / move collections ----
    @classmethod
    def reorder_collections(
        cls, parent_id: int | None, user_id: int, items: Iterable[dict[str, int]]
    ) -> None:
        parent = None
        if parent_id is not None:
            parent = Collection.get_or_none(Collection.id == parent_id)
            if parent:
                cls._require_role(parent, user_id, "editor")
        ids = [item["collection_id"] for item in items]
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
        for item in items:
            col = existing.get(item["collection_id"])
            if not col:
                continue
            col.position = item["position"]
            col.save()

    @classmethod
    def move_collection(
        cls, collection_id: int, user_id: int, parent_id: int | None, position: int | None
    ) -> Collection:
        collection = Collection.get_or_none(
            (Collection.id == collection_id) & (~Collection.is_deleted)
        )
        if not collection:
            raise ResourceNotFoundError("Collection", collection_id)
        cls._require_role(collection, user_id, "owner")

        new_parent = None
        if parent_id is not None:
            new_parent = Collection.get_or_none(
                (Collection.id == parent_id) & (~Collection.is_deleted)
            )
            if not new_parent:
                raise ResourceNotFoundError("Collection", parent_id)
            cls._require_role(new_parent, user_id, "editor")
            ancestor = new_parent
            while ancestor:
                if ancestor.id == collection.id:
                    raise ValueError("Cycle detected")
                ancestor = ancestor.parent

        collection.parent = new_parent
        new_pos = position if position is not None else cls._next_position(parent_id)
        cls._shift_positions(parent_id, new_pos)
        collection.position = new_pos
        collection.updated_at = cls._now()
        collection.save()
        return collection

    # ---- sharing ----
    @classmethod
    def list_acl(cls, collection_id: int, user_id: int) -> list[CollectionCollaborator]:
        collection = Collection.get_or_none(
            (Collection.id == collection_id) & (~Collection.is_deleted)
        )
        if not collection:
            raise ResourceNotFoundError("Collection", collection_id)
        cls._require_role(collection, user_id, "viewer")
        # include owner as implicit collaborator
        collaborators = list(
            CollectionCollaborator.select()
            .where(CollectionCollaborator.collection == collection)
            .order_by(CollectionCollaborator.created_at)
        )
        owner_entry = CollectionCollaborator(
            collection=collection,
            user=User.get_or_none(User.telegram_user_id == collection.user_id),
            role="owner",
            status="active",
            invited_by=None,
        )
        return [owner_entry, *collaborators]

    @classmethod
    def add_collaborator(
        cls, collection_id: int, user_id: int, target_user_id: int, role: Role
    ) -> None:
        collection = Collection.get_or_none(
            (Collection.id == collection_id) & (~Collection.is_deleted)
        )
        if not collection:
            raise ResourceNotFoundError("Collection", collection_id)
        cls._require_role(collection, user_id, "owner")
        if target_user_id == collection.user_id:
            return
        CollectionCollaborator.insert(
            collection=collection,
            user=target_user_id,
            role=role,
            status="active",
            invited_by=user_id,
            created_at=cls._now(),
            updated_at=cls._now(),
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

    @classmethod
    def remove_collaborator(cls, collection_id: int, user_id: int, target_user_id: int) -> None:
        collection = Collection.get_or_none(
            (Collection.id == collection_id) & (~Collection.is_deleted)
        )
        if not collection:
            raise ResourceNotFoundError("Collection", collection_id)
        cls._require_role(collection, user_id, "owner")
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

    @classmethod
    def create_invite(
        cls, collection_id: int, user_id: int, role: Role, expires_at: datetime | None
    ) -> CollectionInvite:
        collection = Collection.get_or_none(
            (Collection.id == collection_id) & (~Collection.is_deleted)
        )
        if not collection:
            raise ResourceNotFoundError("Collection", collection_id)
        cls._require_role(collection, user_id, "owner")
        token = uuid.uuid4().hex
        return CollectionInvite.create(
            collection=collection,
            token=token,
            role=role,
            expires_at=expires_at,
            status="active",
            created_at=cls._now(),
            updated_at=cls._now(),
        )

    @classmethod
    def accept_invite(cls, token: str, user_id: int) -> None:
        invite = CollectionInvite.get_or_none(CollectionInvite.token == token)
        if not invite:
            raise ResourceNotFoundError("Invite", token)
        if invite.status in {"used", "revoked"}:
            raise ResourceNotFoundError("Invite", token)
        if invite.expires_at and invite.expires_at < cls._now():
            invite.status = "expired"
            invite.save()
            raise ResourceNotFoundError("Invite", token)
        collection = invite.collection
        cls.add_collaborator(
            collection.id, collection.user_id, user_id, invite.role
        )  # owner id for audit
        invite.used_at = cls._now()
        invite.status = "used"
        invite.updated_at = cls._now()
        invite.save()
