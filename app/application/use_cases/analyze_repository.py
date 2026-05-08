"""Use case: run LLM analysis on a GitHub repository and refresh its embedding."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from sqlalchemy import select

from app.core.logging_utils import get_logger
from app.db.models.repository import Repository

if TYPE_CHECKING:
    from app.agents.repo_analysis_agent import RepoAnalysisAgent
    from app.core.repo_analysis_schema import RepoAnalysis
    from app.db.session import Database
    from app.infrastructure.embedding.repository_embedding import RepositoryEmbeddingGenerator

logger = get_logger(__name__)


class RepositoryNotFoundError(Exception):
    """Raised when the requested repository row does not exist."""


@dataclass
class RepositoryAnalysisResult:
    """Result returned by :class:`AnalyzeRepositoryUseCase`."""

    repository_id: int
    analysis: RepoAnalysis | None
    cached: bool
    embedding_refreshed: bool


class AnalyzeRepositoryUseCase:
    """Orchestrate LLM analysis and embedding refresh for a repository."""

    def __init__(
        self,
        db: Database,
        agent: RepoAnalysisAgent,
        embedding_gen: RepositoryEmbeddingGenerator,
    ) -> None:
        self._db = db
        self._agent = agent
        self._embedding_gen = embedding_gen

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze(
        self,
        repository_id: int,
        *,
        force: bool = False,
        correlation_id: str,
        chosen_lang: Literal["en", "ru"] = "en",
    ) -> RepositoryAnalysisResult:
        """Run analysis on a repository, honouring content-hash short-circuit.

        Args:
            repository_id: Primary key of the :class:`Repository` row.
            force: When ``True``, bypass the content-hash cache and always
                call the agent.
            correlation_id: Opaque tracing token threaded through logs.
            chosen_lang: Language for the LLM system prompt.

        Returns:
            :class:`RepositoryAnalysisResult` describing what happened.

        Raises:
            :class:`RepositoryNotFoundError`: When no repository with
                ``repository_id`` exists.
        """
        repository = await self._load_repository(repository_id)

        new_content_hash = _compute_content_hash(repository)

        # Cache hit: skip LLM if content unchanged and analysis already exists
        if (
            not force
            and repository.content_hash is not None
            and repository.content_hash == new_content_hash
            and repository.analysis_json is not None
        ):
            logger.info(
                "analyze_repository_cache_hit",
                extra={
                    "event": "analyze_repository_cache_hit",
                    "correlation_id": correlation_id,
                    "repository_id": repository_id,
                    "full_name": repository.full_name,
                },
            )
            existing_analysis = _deserialize_analysis(repository.analysis_json)
            return RepositoryAnalysisResult(
                repository_id=repository_id,
                analysis=existing_analysis,
                cached=True,
                embedding_refreshed=False,
            )

        # Build agent input from the repository row
        from app.core.repo_analysis_schema import RepoAnalysisInput

        languages: dict[str, int] = (
            dict(repository.languages_json)
            if isinstance(repository.languages_json, dict)
            else {}
        )
        topics: list[str] = (
            list(repository.topics_json)
            if isinstance(repository.topics_json, list)
            else []
        )
        agent_input = RepoAnalysisInput(
            full_name=repository.full_name,
            description=repository.description,
            topics=topics,
            primary_language=repository.primary_language,
            languages=languages,
            license_spdx=repository.license_spdx,
            readme_excerpt=repository.readme_excerpt,
            default_branch=repository.default_branch,
        )

        logger.info(
            "analyze_repository_llm_start",
            extra={
                "event": "analyze_repository_llm_start",
                "correlation_id": correlation_id,
                "repository_id": repository_id,
                "full_name": repository.full_name,
                "force": force,
            },
        )

        analysis = await self._agent.analyze(
            agent_input,
            chosen_lang=chosen_lang,
            correlation_id=correlation_id,
        )

        if analysis is None:
            logger.warning(
                "analyze_repository_llm_failed",
                extra={
                    "event": "analyze_repository_llm_failed",
                    "correlation_id": correlation_id,
                    "repository_id": repository_id,
                    "full_name": repository.full_name,
                },
            )
            return RepositoryAnalysisResult(
                repository_id=repository_id,
                analysis=None,
                cached=False,
                embedding_refreshed=False,
            )

        # Persist analysis to the repository row
        await self._persist_analysis(repository, analysis=analysis, content_hash=new_content_hash)

        # Refresh embedding
        await self._embedding_gen.regenerate(
            repository,
            analysis=analysis,
            correlation_id=correlation_id,
        )

        logger.info(
            "analyze_repository_complete",
            extra={
                "event": "analyze_repository_complete",
                "correlation_id": correlation_id,
                "repository_id": repository_id,
                "full_name": repository.full_name,
                "confidence": analysis.confidence,
            },
        )

        return RepositoryAnalysisResult(
            repository_id=repository_id,
            analysis=analysis,
            cached=False,
            embedding_refreshed=True,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _load_repository(self, repository_id: int) -> Repository:
        async with self._db.session() as session:
            stmt = select(Repository).where(Repository.id == repository_id)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()

        if row is None:
            raise RepositoryNotFoundError(repository_id)
        return row

    async def _persist_analysis(
        self,
        repository: Repository,
        *,
        analysis: RepoAnalysis,
        content_hash: str,
    ) -> None:
        async with self._db.transaction() as session:
            # Re-fetch inside the transaction to avoid stale state
            row = await session.get(Repository, repository.id)
            if row is None:
                raise RepositoryNotFoundError(repository.id)

            row.analysis_json = analysis.model_dump()
            row.analysis_model = None  # populated by DI caller when model name is known
            row.analysis_at = datetime.now(UTC)
            row.content_hash = content_hash
            row.pending_analysis = False

        # Refresh the in-memory reference so callers see the updated row
        repository.analysis_json = analysis.model_dump()
        repository.content_hash = content_hash
        repository.pending_analysis = False


# ------------------------------------------------------------------
# Pure helpers (unit-testable without DB)
# ------------------------------------------------------------------


def _compute_content_hash(repository: Repository) -> str:
    """Compute a stable SHA-256 fingerprint from repository content signals."""
    description = repository.description or ""
    topics_raw = repository.topics_json
    sorted_topics = sorted(topics_raw) if isinstance(topics_raw, list) else []
    readme = repository.readme_excerpt or ""

    payload = (
        description
        + "\n"
        + json.dumps(sorted_topics, ensure_ascii=False)
        + "\n"
        + readme
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _deserialize_analysis(analysis_json: dict) -> RepoAnalysis | None:
    """Reconstruct a :class:`RepoAnalysis` from a stored JSON dict."""
    try:
        from app.core.repo_analysis_schema import RepoAnalysis

        return RepoAnalysis.model_validate(analysis_json)
    except Exception:
        logger.warning("analyze_repository_deserialization_failed")
        return None
