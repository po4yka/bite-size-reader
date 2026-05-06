from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.infrastructure.persistence.repositories.aggregation_session_repository import (
    SqliteAggregationSessionRepositoryAdapter,
)
from app.infrastructure.persistence.repositories.audit_log_repository import (
    SqliteAuditLogRepositoryAdapter,
)
from app.infrastructure.persistence.repositories.backup_repository import (
    SqliteBackupRepositoryAdapter,
)
from app.infrastructure.persistence.repositories.batch_session_repository import (
    SqliteBatchSessionRepositoryAdapter,
)
from app.infrastructure.persistence.repositories.crawl_result_repository import (
    SqliteCrawlResultRepositoryAdapter,
)
from app.infrastructure.persistence.repositories.embedding_repository import (
    SqliteEmbeddingRepositoryAdapter,
)
from app.infrastructure.persistence.repositories.import_job_repository import (
    SqliteImportJobRepositoryAdapter,
)
from app.infrastructure.persistence.repositories.llm_repository import (
    SqliteLLMRepositoryAdapter,
)
from app.infrastructure.persistence.repositories.request_repository import (
    SqliteRequestRepositoryAdapter,
)
from app.infrastructure.persistence.repositories.rule_repository import (
    SqliteRuleRepositoryAdapter,
)
from app.infrastructure.persistence.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)
from app.infrastructure.persistence.repositories.tag_repository import (
    SqliteTagRepositoryAdapter,
)
from app.infrastructure.persistence.repositories.topic_search_repository import (
    SqliteTopicSearchRepositoryAdapter,
)
from app.infrastructure.persistence.repositories.user_repository import (
    SqliteUserRepositoryAdapter,
)
from app.infrastructure.persistence.repositories.video_download_repository import (
    SqliteVideoDownloadRepositoryAdapter,
)
from app.infrastructure.persistence.repositories.webhook_repository import (
    SqliteWebhookRepositoryAdapter,
)

if TYPE_CHECKING:
    from app.application.ports.aggregation_sessions import AggregationSessionRepositoryPort
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
    from app.db.session import Database


def build_request_repository(db: Database) -> RequestRepositoryPort:
    return SqliteRequestRepositoryAdapter(db)


def build_aggregation_session_repository(
    db: Database,
) -> AggregationSessionRepositoryPort:
    return SqliteAggregationSessionRepositoryAdapter(db)


def build_summary_repository(db: Database) -> SummaryRepositoryPort:
    return SqliteSummaryRepositoryAdapter(db)


def build_user_repository(db: Database) -> UserRepositoryPort:
    return SqliteUserRepositoryAdapter(db)


def build_llm_repository(db: Database) -> LLMRepositoryPort:
    return SqliteLLMRepositoryAdapter(db)


def build_crawl_result_repository(db: Database) -> CrawlResultRepositoryPort:
    return SqliteCrawlResultRepositoryAdapter(db)


def build_video_download_repository(db: Database) -> VideoDownloadRepositoryPort:
    return SqliteVideoDownloadRepositoryAdapter(db)


def build_audit_log_repository(db: Database) -> AuditLogRepositoryPort:
    return SqliteAuditLogRepositoryAdapter(db)


def build_batch_session_repository(db: Database) -> BatchSessionRepositoryPort:
    return SqliteBatchSessionRepositoryAdapter(db)


def build_topic_search_repository(db: Database) -> TopicSearchRepositoryPort:
    return SqliteTopicSearchRepositoryAdapter(db)


def build_embedding_repository(db: Database) -> EmbeddingRepositoryPort:
    return SqliteEmbeddingRepositoryAdapter(db)


def build_tag_repository(db: Database) -> TagRepositoryPort:
    return SqliteTagRepositoryAdapter(db)


def build_import_job_repository(db: Database) -> ImportJobRepositoryPort:
    return SqliteImportJobRepositoryAdapter(db)


def build_rule_repository(db: Database) -> RuleRepositoryPort:
    return SqliteRuleRepositoryAdapter(db)


def build_webhook_repository(db: Database) -> WebhookRepositoryPort:
    return SqliteWebhookRepositoryAdapter(db)


def build_backup_repository(db: Database) -> BackupRepositoryPort:
    return SqliteBackupRepositoryAdapter(db)


def build_rss_feed_repository(db: Database) -> Any:
    from app.infrastructure.persistence.repositories.rss_feed_repository import (
        SqliteRSSFeedRepositoryAdapter,
    )

    return SqliteRSSFeedRepositoryAdapter(db)
