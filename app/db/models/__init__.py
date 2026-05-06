"""SQLAlchemy model export surface."""

from __future__ import annotations

from app.db.base import Base
from app.db.models.core import (
    CORE_MODELS,
    AttachmentProcessing,
    AudioGeneration,
    AuditLog,
    Chat,
    ClientSecret,
    CrawlResult,
    LLMCall,
    RefreshToken,
    Request,
    Summary,
    SummaryEmbedding,
    TelegramMessage,
    User,
    UserDevice,
    UserInteraction,
    VideoDownload,
)
from app.db.types import _next_server_version, _utcnow, model_to_dict

ALL_MODELS = CORE_MODELS

__all__ = [
    "ALL_MODELS",
    "CORE_MODELS",
    "AttachmentProcessing",
    "AudioGeneration",
    "AuditLog",
    "Base",
    "Chat",
    "ClientSecret",
    "CrawlResult",
    "LLMCall",
    "RefreshToken",
    "Request",
    "Summary",
    "SummaryEmbedding",
    "TelegramMessage",
    "User",
    "UserDevice",
    "UserInteraction",
    "VideoDownload",
    "_next_server_version",
    "_utcnow",
    "model_to_dict",
]
