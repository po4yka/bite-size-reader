"""Collection and collaboration models."""

from __future__ import annotations

import peewee
from playhouse.sqlite_ext import JSONField

from app.db._models_base import BaseModel, _next_server_version, _utcnow
from app.db._models_core import Summary, User


class Collection(BaseModel):
    """User-created collections for organizing summaries."""

    id = peewee.AutoField()
    user = peewee.ForeignKeyField(User, backref="collections", on_delete="CASCADE")
    name = peewee.TextField()
    description = peewee.TextField(null=True)
    parent = peewee.ForeignKeyField("self", backref="children", null=True, on_delete="SET NULL")
    position = peewee.IntegerField(null=True)
    server_version = peewee.BigIntegerField(default=_next_server_version)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)
    is_shared = peewee.BooleanField(default=False)
    share_count = peewee.IntegerField(default=0)
    is_deleted = peewee.BooleanField(default=False)
    deleted_at = peewee.DateTimeField(null=True)
    collection_type = peewee.TextField(default="manual")
    query_conditions_json = JSONField(null=True)
    query_match_mode = peewee.TextField(default="all")
    last_evaluated_at = peewee.DateTimeField(null=True)

    class Meta:
        table_name = "collections"
        indexes = (
            (("user", "name"), True),
            (("user", "parent", "name"), False),
            (("updated_at",), False),
            (("parent", "position"), False),
            (("collection_type",), False),
        )


class CollectionItem(BaseModel):
    """Link table for items in a collection."""

    id = peewee.AutoField()
    collection = peewee.ForeignKeyField(Collection, backref="items", on_delete="CASCADE")
    summary = peewee.ForeignKeyField(Summary, backref="collection_items", on_delete="CASCADE")
    position = peewee.IntegerField(null=True)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "collection_items"
        indexes = (
            (("collection", "summary"), True),
            (("collection", "position"), False),
        )


class CollectionCollaborator(BaseModel):
    """Collaborators on a collection."""

    id = peewee.AutoField()
    collection = peewee.ForeignKeyField(Collection, backref="collaborators", on_delete="CASCADE")
    user = peewee.ForeignKeyField(User, backref="collection_collaborations", on_delete="CASCADE")
    role = peewee.TextField()
    status = peewee.TextField(default="active")
    invited_by = peewee.ForeignKeyField(User, backref="collection_invites_sent", null=True)
    server_version = peewee.BigIntegerField(default=_next_server_version)
    created_at = peewee.DateTimeField(default=_utcnow)
    updated_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "collection_collaborators"
        indexes = (
            (("collection", "user"), True),
            (("user",), False),
        )


class CollectionInvite(BaseModel):
    """Invite tokens for collection collaboration."""

    id = peewee.AutoField()
    collection = peewee.ForeignKeyField(Collection, backref="invites", on_delete="CASCADE")
    token = peewee.TextField(unique=True)
    role = peewee.TextField()
    expires_at = peewee.DateTimeField(null=True)
    used_at = peewee.DateTimeField(null=True)
    invited_email = peewee.TextField(null=True)
    invited_user_id = peewee.BigIntegerField(null=True)
    status = peewee.TextField(default="active")
    server_version = peewee.BigIntegerField(default=_next_server_version)
    created_at = peewee.DateTimeField(default=_utcnow)
    updated_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "collection_invites"
        indexes = (
            (("collection",), False),
            (("status",), False),
        )
