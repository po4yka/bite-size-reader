"""Embedding generator for GitHub repository entities."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.logging_utils import get_logger
from app.db.models.repository import Repository, RepositoryEmbedding
from app.infrastructure.vector.point_ids import repository_point_id

if TYPE_CHECKING:
    from app.core.repo_analysis_schema import RepoAnalysis
    from app.db.session import Database
    from app.infrastructure.embedding.embedding_protocol import EmbeddingServiceProtocol
    from app.infrastructure.vector.qdrant_store import QdrantVectorStore

logger = get_logger(__name__)


class RepositoryEmbeddingGenerator:
    """Generates and persists embeddings for GitHub repository entities.

    Idempotent: re-running with the same repository overwrites the existing
    RepositoryEmbedding row and Qdrant point.
    """

    def __init__(
        self,
        embedding_service: EmbeddingServiceProtocol,
        qdrant_store: QdrantVectorStore | None,
        db: Database,
        *,
        environment: str,
        user_scope: str,
    ) -> None:
        self._embedding_service = embedding_service
        self._qdrant = qdrant_store
        self._db = db
        self._environment = environment
        self._user_scope = user_scope

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def regenerate(
        self,
        repository: Repository,
        *,
        analysis: RepoAnalysis | None,
        correlation_id: str,
    ) -> RepositoryEmbedding:
        """Compose embedding text, generate vector, upsert DB row and Qdrant.

        Returns the persisted RepositoryEmbedding row.
        """
        languages: list[str] = (
            list(repository.languages_json.keys())
            if isinstance(repository.languages_json, dict)
            else []
        )
        topics: list[str] = (
            list(repository.topics_json) if isinstance(repository.topics_json, list) else []
        )

        text = self.compose_embedding_text(
            full_name=repository.full_name,
            description=repository.description,
            topics=topics,
            primary_language=repository.primary_language,
            languages=languages,
            analysis=analysis,
            readme_excerpt=repository.readme_excerpt,
        )

        model_name = self._embedding_service.get_model_name(None)
        dimensions = self._embedding_service.get_dimensions(None)

        embedding = await self._embedding_service.generate_embedding(
            text,
            language=None,
            task_type="document",
        )
        embedding_blob = self._embedding_service.serialize_embedding(embedding)

        model_version = "1.0"

        db_row = await self._upsert_db_row(
            repository_id=repository.id,
            model_name=model_name,
            model_version=model_version,
            embedding_blob=embedding_blob,
            dimensions=dimensions,
            language=None,
        )

        await self._upsert_qdrant(
            repository=repository,
            topics=topics,
            embedding=embedding,
            correlation_id=correlation_id,
        )

        logger.info(
            "repository_embedding_regenerated",
            extra={
                "event": "repository_embedding_regenerated",
                "correlation_id": correlation_id,
                "repository_id": repository.id,
                "full_name": repository.full_name,
                "model_name": model_name,
                "dimensions": dimensions,
            },
        )

        return db_row

    @staticmethod
    def compose_embedding_text(
        *,
        full_name: str,
        description: str | None,
        topics: list[str],
        primary_language: str | None,
        languages: list[str],
        analysis: RepoAnalysis | None,
        readme_excerpt: str | None,
        max_chars: int = 2000,
    ) -> str:
        """Compose weighted embedding text from repository metadata.

        Concatenation order (higher weight = earlier in string):
        1. full_name repeated twice
        2. description repeated twice
        3. analysis.purpose
        4. topics joined
        5. primary_language + languages joined
        6. analysis.tech_stack joined
        7. analysis.architecture_summary (truncated to 500 chars)
        8. readme_excerpt (truncated to remaining budget)

        Total capped at max_chars.
        """
        parts: list[str] = []

        # full_name x2
        parts.append(full_name)
        parts.append(full_name)

        # description x2
        if description:
            parts.append(description)
            parts.append(description)

        # analysis fields
        if analysis is not None:
            parts.append(analysis.purpose)
            if analysis.tech_stack:
                parts.append(" ".join(analysis.tech_stack))

        # topics
        if topics:
            parts.append(" ".join(topics))

        # languages
        lang_parts: list[str] = []
        if primary_language:
            lang_parts.append(primary_language)
        if languages:
            lang_parts.extend(lang for lang in languages if lang != primary_language)
        if lang_parts:
            parts.append(" ".join(lang_parts))

        # architecture summary (capped)
        if analysis is not None and analysis.architecture_summary:
            parts.append(analysis.architecture_summary[:500])

        # assemble all non-readme parts first
        text = " ".join(parts)
        if len(text) >= max_chars:
            return text[:max_chars]

        # append readme excerpt in remaining budget
        if readme_excerpt:
            remaining = max_chars - len(text) - 1  # -1 for separator space
            if remaining > 0:
                text = text + " " + readme_excerpt[:remaining]

        return text[:max_chars]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _upsert_db_row(
        self,
        *,
        repository_id: int,
        model_name: str,
        model_version: str,
        embedding_blob: bytes,
        dimensions: int,
        language: str | None,
    ) -> RepositoryEmbedding:
        """Upsert RepositoryEmbedding row keyed by repository_id."""
        async with self._db.transaction() as session:
            stmt = (
                pg_insert(RepositoryEmbedding)
                .values(
                    repository_id=repository_id,
                    model_name=model_name,
                    model_version=model_version,
                    embedding_blob=embedding_blob,
                    dimensions=dimensions,
                    language=language,
                )
                .on_conflict_do_update(
                    index_elements=["repository_id"],
                    set_={
                        "model_name": model_name,
                        "model_version": model_version,
                        "embedding_blob": embedding_blob,
                        "dimensions": dimensions,
                        "language": language,
                    },
                )
                .returning(RepositoryEmbedding.id)
            )
            result = await session.execute(stmt)
            row_id = result.scalar_one()

        async with self._db.session() as session:
            row = await session.get(RepositoryEmbedding, row_id)

        assert row is not None  # just inserted above — cannot be None
        return row

    async def _upsert_qdrant(
        self,
        *,
        repository: Repository,
        topics: list[str],
        embedding: Any,
        correlation_id: str,
    ) -> None:
        if self._qdrant is None or not self._qdrant.available:
            logger.debug(
                "repository_embedding_qdrant_skipped",
                extra={
                    "reason": "not_available",
                    "repository_id": repository.id,
                    "correlation_id": correlation_id,
                },
            )
            return

        point_id = repository_point_id(
            self._environment,
            self._user_scope,
            repository.id,
        )

        created_at_iso = (
            repository.created_at.isoformat() if repository.created_at is not None else None
        )

        metadata: dict[str, Any] = {
            "entity_type": "repository",
            "repository_id": repository.id,
            "user_id": repository.user_id,
            "github_id": repository.github_id,
            "full_name": repository.full_name,
            "primary_language": repository.primary_language,
            "topics": topics,
            "is_starred": repository.is_starred,
            "source": repository.source.value
            if hasattr(repository.source, "value")
            else repository.source,
            "created_at": created_at_iso,
            "environment": self._environment,
            "user_scope": self._user_scope,
            "language": "en",
        }

        vector: list[float] = (
            embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
        )

        await asyncio.to_thread(
            self._qdrant.upsert_notes,
            [vector],
            [metadata],
            [point_id],
        )
