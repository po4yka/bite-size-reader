"""Message routing and coordination for Telegram bot."""

# ruff: noqa: E501
# flake8: noqa

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.adapters.repository_ports import (
    UserRepositoryPort,
    create_user_repository,
)
from app.adapters.telegram.message_router_content import MessageRouterContentMixin
from app.adapters.telegram.message_router_entrypoint import MessageRouterEntrypointMixin
from app.adapters.telegram.message_router_interactions import MessageRouterInteractionsMixin
from app.adapters.telegram.message_router_rate_limiter import MessageRouterRateLimiterMixin
from app.adapters.telegram.task_manager import UserTaskManager
from app.config import AppConfig
from app.db.session import DatabaseSessionManager
from app.security.rate_limiter import RateLimitConfig, RedisUserRateLimiter, UserRateLimiter

if TYPE_CHECKING:
    from app.adapters.attachment.attachment_processor import AttachmentProcessor
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.telegram.access_controller import AccessController
    from app.adapters.telegram.command_processor import CommandProcessor
    from app.adapters.telegram.forward_processor import ForwardProcessor
    from app.adapters.telegram.url_handler import URLHandler

logger = logging.getLogger(__name__)


class MessageRouter(
    MessageRouterEntrypointMixin,
    MessageRouterContentMixin,
    MessageRouterRateLimiterMixin,
    MessageRouterInteractionsMixin,
):
    """Main message routing and coordination logic."""

    # ruff: noqa: E501

    def __init__(
        self,
        cfg: AppConfig,
        db: DatabaseSessionManager,
        access_controller: AccessController,
        command_processor: CommandProcessor,
        url_handler: URLHandler,
        forward_processor: ForwardProcessor,
        response_formatter: ResponseFormatter,
        audit_func: Callable[[str, str, dict], None],
        task_manager: UserTaskManager | None = None,
        attachment_processor: AttachmentProcessor | None = None,
        user_repo: UserRepositoryPort | None = None,
        lang: str = "en",
    ) -> None:
        self.cfg = cfg
        self.db = db
        self._lang = lang
        self.user_repo = user_repo or create_user_repository(db)
        self.access_controller = access_controller
        self.command_processor = command_processor
        self.url_handler = url_handler
        self.forward_processor = forward_processor
        self.attachment_processor = attachment_processor
        self.response_formatter = response_formatter
        self._audit = audit_func
        self._task_manager = task_manager
        self.callback_handler: Any | None = None

        self._rate_limiter_config = RateLimitConfig(
            max_requests=cfg.api_limits.requests_limit,
            window_seconds=cfg.api_limits.window_seconds,
            max_concurrent=cfg.api_limits.max_concurrent,
            cooldown_multiplier=cfg.api_limits.cooldown_multiplier,
        )
        self._rate_limiter = UserRateLimiter(self._rate_limiter_config)
        self._redis_limiter: RedisUserRateLimiter | None = None
        self._redis_limiter_available: bool | None = None
        self._rate_limit_notified_until: dict[int, float] = {}
        self._rate_limit_notice_window = max(self._rate_limiter_config.window_seconds, 30)
        self._recent_message_ids: dict[tuple[int, int, int], tuple[float, str]] = {}
        self._recent_message_ttl = 120
