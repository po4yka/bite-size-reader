"""Compatibility facade for application-layer ports.

Production code should import from specific submodules under
``app.application.ports``. This module re-exports the complete surface for
tests and incremental migration.
"""

from __future__ import annotations

from .audio import AudioGenerationRepositoryPort, AudioStoragePort, TTSProviderPort
from .imports import BookmarkImportPort, ImportJobRepositoryPort
from .requests import (
    CrawlResultRepositoryPort,
    LLMCallRecord,
    LLMRepositoryPort,
    RequestRepositoryPort,
    VideoDownloadRepositoryPort,
)
from .rules import (
    CollectionMembershipPort,
    RuleContextPort,
    RuleRateLimiterPort,
    RuleRepositoryPort,
    WebhookDispatchPort,
    WebhookRepositoryPort,
)
from .search import (
    EmbeddingProviderPort,
    EmbeddingRepositoryPort,
    TopicSearchRepositoryPort,
    VectorSearchPort,
)
from .summaries import SummaryRepositoryPort, TagRepositoryPort
from .users import (
    AuditLogRepositoryPort,
    BackupRepositoryPort,
    BatchSessionRepositoryPort,
    KarakeepSyncRepositoryPort,
    UserRepositoryPort,
)

__all__ = [
    "AudioGenerationRepositoryPort",
    "AudioStoragePort",
    "AuditLogRepositoryPort",
    "BackupRepositoryPort",
    "BatchSessionRepositoryPort",
    "BookmarkImportPort",
    "CollectionMembershipPort",
    "CrawlResultRepositoryPort",
    "EmbeddingProviderPort",
    "EmbeddingRepositoryPort",
    "ImportJobRepositoryPort",
    "KarakeepSyncRepositoryPort",
    "LLMCallRecord",
    "LLMRepositoryPort",
    "RequestRepositoryPort",
    "RuleContextPort",
    "RuleRateLimiterPort",
    "RuleRepositoryPort",
    "SummaryRepositoryPort",
    "TTSProviderPort",
    "TagRepositoryPort",
    "TopicSearchRepositoryPort",
    "UserRepositoryPort",
    "VectorSearchPort",
    "VideoDownloadRepositoryPort",
    "WebhookDispatchPort",
    "WebhookRepositoryPort",
]
