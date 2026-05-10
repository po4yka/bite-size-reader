"""Verify UUID parity between CocoIndex flow and QdrantVectorStore.

If this test fails, the CocoIndex flow and the fast path will write to
*different* Qdrant point IDs, causing duplicate points.
"""

from __future__ import annotations

import uuid

import pytest


_UUID_NAMESPACE = uuid.NAMESPACE_OID


def _expected_uuid(request_id: int, summary_id: int) -> str:
    """Replicate qdrant_store._str_to_uuid(f'{request_id}:{summary_id}')."""
    return str(uuid.uuid5(_UUID_NAMESPACE, f"{request_id}:{summary_id}"))


@pytest.mark.parametrize(
    ("request_id", "summary_id"),
    [
        (1, 1),
        (42, 100),
        (999, 12345),
        (0, 0),
        (2**31 - 1, 2**31 - 1),
    ],
)
def test_point_id_matches_qdrant_store(request_id: int, summary_id: int) -> None:
    from app.infrastructure.cocoindex.embedding_bridge import summary_id_to_point_id
    from app.infrastructure.vector.qdrant_store import _str_to_uuid

    expected = _str_to_uuid(f"{request_id}:{summary_id}")
    actual = summary_id_to_point_id(request_id, summary_id)

    assert actual == expected, (
        f"UUID mismatch for request_id={request_id}, summary_id={summary_id}: "
        f"fast path produces {expected!r}, CocoIndex flow produces {actual!r}. "
        "This would create duplicate Qdrant points — fix the key format in embedding_bridge.py."
    )


def test_point_ids_are_unique_across_summaries() -> None:
    from app.infrastructure.cocoindex.embedding_bridge import summary_id_to_point_id

    ids = {summary_id_to_point_id(req, s) for req, s in [(1, 1), (1, 2), (2, 1), (2, 2)]}
    assert len(ids) == 4, "Point IDs must be unique across different (request_id, summary_id) pairs"


def test_point_id_is_deterministic() -> None:
    from app.infrastructure.cocoindex.embedding_bridge import summary_id_to_point_id

    first = summary_id_to_point_id(42, 100)
    second = summary_id_to_point_id(42, 100)
    assert first == second, "Point ID must be deterministic (same input → same output)"
