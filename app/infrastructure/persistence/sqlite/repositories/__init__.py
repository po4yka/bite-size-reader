"""SQLite repository adapters.

This package contains repository adapters that implement domain repository
interfaces using SQLite/Peewee as the persistence layer.
"""

from app.infrastructure.persistence.sqlite.repositories.audit_log_repository import (
    SqliteAuditLogRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.collection_repository import (
    SqliteCollectionRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.crawl_result_repository import (
    SqliteCrawlResultRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.embedding_repository import (
    SqliteEmbeddingRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.latency_stats_repository import (
    LatencyStats,
    SqliteLatencyStatsRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.llm_repository import (
    SqliteLLMRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.request_repository import (
    SqliteRequestRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.telegram_message_repository import (
    SqliteTelegramMessageRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.user_repository import (
    SqliteUserRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.video_download_repository import (
    SqliteVideoDownloadRepositoryAdapter,
)

__all__ = [
    "LatencyStats",
    "SqliteAuditLogRepositoryAdapter",
    "SqliteCollectionRepositoryAdapter",
    "SqliteCrawlResultRepositoryAdapter",
    "SqliteEmbeddingRepositoryAdapter",
    "SqliteLLMRepositoryAdapter",
    "SqliteLatencyStatsRepositoryAdapter",
    "SqliteRequestRepositoryAdapter",
    "SqliteSummaryRepositoryAdapter",
    "SqliteTelegramMessageRepositoryAdapter",
    "SqliteUserRepositoryAdapter",
    "SqliteVideoDownloadRepositoryAdapter",
]
