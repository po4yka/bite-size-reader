from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.infrastructure.persistence.sqlite.repositories.audit_log_repository import (
    SqliteAuditLogRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.backup_repository import (
    SqliteBackupRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.batch_session_repository import (
    SqliteBatchSessionRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.crawl_result_repository import (
    SqliteCrawlResultRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.embedding_repository import (
    SqliteEmbeddingRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.import_job_repository import (
    SqliteImportJobRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.llm_repository import (
    SqliteLLMRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.request_repository import (
    SqliteRequestRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.rule_repository import (
    SqliteRuleRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.tag_repository import (
    SqliteTagRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.topic_search_repository import (
    SqliteTopicSearchRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.user_repository import (
    SqliteUserRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.video_download_repository import (
    SqliteVideoDownloadRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.webhook_repository import (
    SqliteWebhookRepositoryAdapter,
)

if TYPE_CHECKING:
    from app.application.ports.audit import AuditLogRepositoryPort
    from app.application.ports.backups import BackupRepositoryPort
    from app.application.ports.batch_sessions import BatchSessionRepositoryPort
    from app.application.ports.imports import ImportJobRepositoryPort
    from app.application.ports.requests import (
        CrawlResultRepositoryPort,
        LLMRepositoryPort,
        RequestRepositoryPort,
        VideoDownloadRepositoryPort,
    )
    from app.application.ports.rules import RuleRepositoryPort, WebhookRepositoryPort
    from app.application.ports.search import EmbeddingRepositoryPort, TopicSearchRepositoryPort
    from app.application.ports.summaries import SummaryRepositoryPort, TagRepositoryPort
    from app.application.ports.users import UserRepositoryPort
    from app.db.session import DatabaseSessionManager


def build_request_repository(db: DatabaseSessionManager) -> RequestRepositoryPort:
    return SqliteRequestRepositoryAdapter(db)


def build_summary_repository(db: DatabaseSessionManager) -> SummaryRepositoryPort:
    return SqliteSummaryRepositoryAdapter(db)


def build_user_repository(db: DatabaseSessionManager) -> UserRepositoryPort:
    return SqliteUserRepositoryAdapter(db)


def build_llm_repository(db: DatabaseSessionManager) -> LLMRepositoryPort:
    return SqliteLLMRepositoryAdapter(db)


def build_crawl_result_repository(db: DatabaseSessionManager) -> CrawlResultRepositoryPort:
    return SqliteCrawlResultRepositoryAdapter(db)


def build_video_download_repository(db: DatabaseSessionManager) -> VideoDownloadRepositoryPort:
    return SqliteVideoDownloadRepositoryAdapter(db)


def build_audit_log_repository(db: DatabaseSessionManager) -> AuditLogRepositoryPort:
    return SqliteAuditLogRepositoryAdapter(db)


def build_batch_session_repository(db: DatabaseSessionManager) -> BatchSessionRepositoryPort:
    return SqliteBatchSessionRepositoryAdapter(db)


def build_topic_search_repository(db: DatabaseSessionManager) -> TopicSearchRepositoryPort:
    return SqliteTopicSearchRepositoryAdapter(db)


def build_embedding_repository(db: DatabaseSessionManager) -> EmbeddingRepositoryPort:
    return SqliteEmbeddingRepositoryAdapter(db)


def build_tag_repository(db: DatabaseSessionManager) -> TagRepositoryPort:
    return SqliteTagRepositoryAdapter(db)


def build_import_job_repository(db: DatabaseSessionManager) -> ImportJobRepositoryPort:
    return SqliteImportJobRepositoryAdapter(db)


def build_rule_repository(db: DatabaseSessionManager) -> RuleRepositoryPort:
    return SqliteRuleRepositoryAdapter(db)


def build_webhook_repository(db: DatabaseSessionManager) -> WebhookRepositoryPort:
    return SqliteWebhookRepositoryAdapter(db)


def build_backup_repository(db: DatabaseSessionManager) -> BackupRepositoryPort:
    return SqliteBackupRepositoryAdapter(db)


def build_rss_feed_repository(db: DatabaseSessionManager) -> Any:
    from app.infrastructure.persistence.sqlite.repositories.rss_feed_repository import (
        SqliteRSSFeedRepositoryAdapter,
    )

    return SqliteRSSFeedRepositoryAdapter(db)
