"""Deterministic Qdrant point IDs shared by fast-path and CocoIndex writers."""

from __future__ import annotations

import uuid

_UUID_NAMESPACE = uuid.NAMESPACE_OID


def str_to_uuid(value: str) -> str:
    """Hash an arbitrary string to a deterministic UUID string."""
    return str(uuid.uuid5(_UUID_NAMESPACE, value))


def summary_point_id(request_id: int, summary_id: int) -> str:
    """Compute the Qdrant point UUID for a summary entity."""
    return str_to_uuid(f"{request_id}:{summary_id}")


def repository_point_id(environment: str, user_scope: str, repository_id: int) -> str:
    """Compute the Qdrant point UUID for a repository entity."""
    return str_to_uuid(f"{environment}:{user_scope}:repository:{repository_id}")
