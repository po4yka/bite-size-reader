"""Invite operations for the SQLite collection repository."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from app.core.time_utils import coerce_datetime
from app.db.models import CollectionCollaborator, CollectionInvite, model_to_dict

from ._collection_repo_shared import _get_active_collection, _now, _recompute_share_state
from ._repository_mixin_base import SqliteRepositoryMixinBase

if TYPE_CHECKING:
    import datetime as dt


class CollectionRepositoryInviteMixin(SqliteRepositoryMixinBase):
    """Collection invite lifecycle operations."""

    async def async_create_invite(
        self,
        collection_id: int,
        role: str,
        expires_at: dt.datetime | None,
    ) -> dict[str, Any]:
        """Create an invite for a collection."""

        def _create() -> dict[str, Any]:
            collection = _get_active_collection(collection_id)
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
        """Get an invite by token."""

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

    async def async_accept_invite(
        self,
        token: str,
        user_id: int,
    ) -> dict[str, Any] | None:
        """Accept an invite and add the user as collaborator."""

        def _accept() -> dict[str, Any] | None:
            invite = CollectionInvite.get_or_none(CollectionInvite.token == token)
            if not invite:
                return None
            if invite.status in {"used", "revoked"}:
                return None
            expires_at = (
                coerce_datetime(invite.expires_at) if invite.expires_at is not None else None
            )
            if expires_at and expires_at < _now():
                invite.status = "expired"
                invite.save()
                return None

            collection = invite.collection
            if not collection or collection.is_deleted:
                return None

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
                _recompute_share_state(collection)

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
