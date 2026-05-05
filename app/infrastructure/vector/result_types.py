"""Backend-neutral result types for vector store queries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class VectorQueryHit:
    """A single hit from a vector similarity query.

    ``distance`` is normalised to the range [0, 2] where 0 means identical and
    higher values mean less similar.  The Qdrant adapter converts its native
    similarity score to this convention before populating this field.
    """

    id: str
    distance: float
    metadata: dict[str, Any]


@dataclass(frozen=True)
class VectorQueryResult:
    """Collection of hits returned by a vector store query."""

    hits: list[VectorQueryHit] = field(default_factory=list)

    @classmethod
    def empty(cls) -> VectorQueryResult:
        return cls(hits=[])
