"""Deterministic Qdrant point IDs shared by fast-path and CocoIndex writers."""

from __future__ import annotations

import uuid

_UUID_NAMESPACE = uuid.NAMESPACE_OID


def summary_point_id(request_id: int, summary_id: int) -> str:
    """Compute the Qdrant point UUID for a summary entity."""
    return str(uuid.uuid5(_UUID_NAMESPACE, f"{request_id}:{summary_id}"))


def repository_point_id(environment: str, user_scope: str, repository_id: int) -> str:
    """Compute the Qdrant point UUID for a repository entity."""
    return str(
        uuid.uuid5(_UUID_NAMESPACE, f"{environment}:{user_scope}:repository:{repository_id}")
    )
