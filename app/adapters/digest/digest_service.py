"""Digest service -- orchestrates reader + analyzer + formatter + delivery."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any

from app.db.models import Channel, ChannelSubscription, DigestDelivery, _utcnow

if TYPE_CHECKING:
    from app.adapters.digest.analyzer import DigestAnalyzer
    from app.adapters.digest.channel_reader import ChannelReader
    from app.adapters.digest.formatter import DigestFormatter
    from app.config import AppConfig

logger = logging.getLogger(__name__)


@dataclass
class DigestResult:
    """Result of a digest generation."""

    user_id: int
    post_count: int = 0
    channel_count: int = 0
    digest_type: str = "on_demand"
    correlation_id: str = ""
    messages_sent: int = 0
    errors: list[str] = field(default_factory=list)


class DigestService:
    """Orchestrates channel reading, analysis, formatting, and delivery."""

    def __init__(
        self,
        cfg: AppConfig,
        reader: ChannelReader,
        analyzer: DigestAnalyzer,
        formatter: DigestFormatter,
        send_message_func: Any,  # async callable(user_id, text, reply_markup=...)
    ) -> None:
        self._cfg = cfg
        self._reader = reader
        self._analyzer = analyzer
        self._formatter = formatter
        self._send = send_message_func

    async def generate_digest(
        self,
        user_id: int,
        correlation_id: str,
        digest_type: str = "on_demand",
        lang: str = "en",
    ) -> DigestResult:
        """Generate and deliver a digest to a user.

        Args:
            user_id: Telegram user ID.
            correlation_id: Correlation ID for tracing.
            digest_type: 'scheduled' or 'on_demand'.
            lang: Language for LLM analysis prompts.

        Returns:
            DigestResult with delivery statistics.
        """
        result = DigestResult(
            user_id=user_id,
            digest_type=digest_type,
            correlation_id=correlation_id,
        )

        # 1. Fetch posts
        try:
            posts = await self._reader.fetch_posts_for_user(user_id)
        except Exception as e:
            logger.exception("digest_fetch_failed", extra={"cid": correlation_id, "uid": user_id})
            result.errors.append(f"Fetch failed: {e}")
            return result

        if not posts:
            logger.info("digest_no_posts", extra={"cid": correlation_id, "uid": user_id})
            try:
                await self._send(
                    user_id,
                    "\u041d\u0435\u0442 \u043d\u043e\u0432\u044b\u0445 \u043f\u043e\u0441\u0442\u043e\u0432 \u0432 \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043d\u043d\u044b\u0445 \u043a\u0430\u043d\u0430\u043b\u0430\u0445.",
                )
                result.messages_sent = 1
            except Exception as e:
                result.errors.append(f"Send failed: {e}")
            return result

        # 2-5. Analyze, filter, format, deliver, persist
        return await self._process_and_deliver(posts, result, correlation_id, lang)

    async def generate_channel_digest(
        self,
        user_id: int,
        channel: Channel,
        correlation_id: str,
        lang: str = "en",
    ) -> DigestResult:
        """Generate a digest for a single channel's unread posts.

        Args:
            user_id: Telegram user ID.
            channel: Channel record to digest.
            correlation_id: Correlation ID for tracing.
            lang: Language for LLM analysis prompts.

        Returns:
            DigestResult with delivery statistics.
        """
        result = DigestResult(
            user_id=user_id,
            digest_type="channel_on_demand",
            correlation_id=correlation_id,
        )

        # 1. Fetch unread posts from the single channel
        try:
            posts = await self._reader.fetch_posts_for_channel(channel, user_id)
        except Exception as e:
            logger.exception(
                "cdigest_fetch_failed",
                extra={"cid": correlation_id, "uid": user_id, "channel": channel.username},
            )
            result.errors.append(f"Fetch failed: {e}")
            return result

        if not posts:
            logger.info(
                "cdigest_no_unread",
                extra={"cid": correlation_id, "uid": user_id, "channel": channel.username},
            )
            try:
                await self._send(
                    user_id,
                    f"\u041d\u0435\u0442 \u043d\u0435\u043f\u0440\u043e\u0447\u0438\u0442\u0430\u043d\u043d\u044b\u0445 \u043f\u043e\u0441\u0442\u043e\u0432 \u0432 @{channel.username}.",
                )
                result.messages_sent = 1
            except Exception as e:
                result.errors.append(f"Send failed: {e}")
            return result

        # 2-5. Analyze, filter, format, deliver, persist
        return await self._process_and_deliver(posts, result, correlation_id, lang)

    async def _process_and_deliver(
        self,
        posts: list[dict[str, Any]],
        result: DigestResult,
        correlation_id: str,
        lang: str,
    ) -> DigestResult:
        """Shared pipeline: analyze, filter, format, deliver, persist.

        Args:
            posts: Raw posts to process.
            result: DigestResult to populate.
            correlation_id: Correlation ID for tracing.
            lang: Language for LLM analysis prompts.

        Returns:
            Populated DigestResult.
        """
        user_id = result.user_id

        # 2. Analyze posts
        try:
            analyzed = await self._analyzer.analyze_posts(posts, correlation_id, lang)
        except Exception as e:
            logger.exception("digest_analysis_failed", extra={"cid": correlation_id})
            result.errors.append(f"Analysis failed: {e}")
            return result

        if not analyzed:
            try:
                await self._send(
                    user_id,
                    "\u041f\u043e\u0441\u0442\u044b \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u044b, \u043d\u043e \u0430\u043d\u0430\u043b\u0438\u0437 \u043d\u0435 \u0434\u0430\u043b \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u043e\u0432.",
                )
                result.messages_sent = 1
            except Exception as e:
                result.errors.append(f"Send failed: {e}")
            return result

        # 2b. Filter out ads and announcements
        pre_filter_count = len(analyzed)
        analyzed = [
            p
            for p in analyzed
            if not p.get("is_ad", False) and p.get("content_type") != "announcement"
        ]
        filtered_count = pre_filter_count - len(analyzed)
        if filtered_count:
            logger.info(
                "digest_filtered_posts",
                extra={
                    "cid": correlation_id,
                    "filtered": filtered_count,
                    "remaining": len(analyzed),
                },
            )

        if not analyzed:
            try:
                await self._send(
                    user_id,
                    "\u0412\u0441\u0435 \u043f\u043e\u0441\u0442\u044b \u043e\u0442\u0444\u0438\u043b\u044c\u0442\u0440\u043e\u0432\u0430\u043d\u044b (\u0440\u0435\u043a\u043b\u0430\u043c\u0430/\u0430\u043d\u043e\u043d\u0441\u044b). \u041d\u0435\u0447\u0435\u0433\u043e \u043f\u043e\u043a\u0430\u0437\u044b\u0432\u0430\u0442\u044c.",
                )
                result.messages_sent = 1
            except Exception as e:
                result.errors.append(f"Send failed: {e}")
            return result

        # 2c. Cross-channel deduplication by fuzzy topic matching
        pre_dedup_count = len(analyzed)
        analyzed = _deduplicate_posts(analyzed)
        dedup_dropped = pre_dedup_count - len(analyzed)
        if dedup_dropped:
            logger.info(
                "digest_dedup_dropped",
                extra={"cid": correlation_id, "dropped": dedup_dropped},
            )

        # 2d. Filter by minimum relevance score
        min_rel = self._cfg.digest.min_relevance_score
        pre_rel_count = len(analyzed)
        analyzed = [p for p in analyzed if p.get("relevance_score", 0) >= min_rel]
        rel_dropped = pre_rel_count - len(analyzed)
        if rel_dropped:
            logger.info(
                "digest_low_relevance_dropped",
                extra={
                    "cid": correlation_id,
                    "dropped": rel_dropped,
                    "threshold": min_rel,
                },
            )

        if not analyzed:
            try:
                await self._send(
                    user_id,
                    "\u0412\u0441\u0435 \u043f\u043e\u0441\u0442\u044b \u043e\u0442\u0444\u0438\u043b\u044c\u0442\u0440\u043e\u0432\u0430\u043d\u044b (\u0440\u0435\u043a\u043b\u0430\u043c\u0430, \u0434\u0443\u0431\u043b\u0438 \u0438\u043b\u0438 \u043d\u0438\u0437\u043a\u0430\u044f \u0440\u0435\u043b\u0435\u0432\u0430\u043d\u0442\u043d\u043e\u0441\u0442\u044c).",
                )
                result.messages_sent = 1
            except Exception as e:
                result.errors.append(f"Send failed: {e}")
            return result

        # 3. Format digest
        message_chunks = self._formatter.format_digest(analyzed)

        # Count unique channels
        channels_seen = {p.get("_channel_username") for p in analyzed if p.get("_channel_username")}
        result.post_count = len(analyzed)
        result.channel_count = len(channels_seen)

        # 4. Deliver via bot
        for text, buttons in message_chunks:
            try:
                reply_markup = _build_inline_keyboard(buttons) if buttons else None
                await self._send(user_id, text, reply_markup=reply_markup)
                result.messages_sent += 1
            except Exception as e:
                logger.warning(
                    "digest_send_chunk_failed",
                    extra={"cid": correlation_id, "error": str(e)},
                )
                result.errors.append(f"Send failed: {e}")

        # 5. Persist delivery record
        post_ids = [p.get("message_id") for p in analyzed]
        try:
            DigestDelivery.create(
                user=user_id,
                delivered_at=_utcnow(),
                post_count=result.post_count,
                channel_count=result.channel_count,
                digest_type=result.digest_type,
                correlation_id=correlation_id,
                posts_json=post_ids,
            )
        except Exception as exc:
            logger.error(
                "digest_delivery_persist_failed",
                extra={
                    "cid": correlation_id,
                    "uid": user_id,
                    "post_ids_sample": post_ids[:5],
                    "error": str(exc),
                },
            )
            result.errors.append(f"Delivery record not saved: {exc}")

        logger.info(
            "digest_delivered",
            extra={
                "cid": correlation_id,
                "uid": user_id,
                "posts": result.post_count,
                "channels": result.channel_count,
                "messages": result.messages_sent,
                "type": result.digest_type,
            },
        )
        return result

    @staticmethod
    def get_users_with_subscriptions() -> list[int]:
        """Return user IDs that have at least one active subscription."""
        rows = (
            ChannelSubscription.select(ChannelSubscription.user)
            .where(ChannelSubscription.is_active == True)  # noqa: E712
            .distinct()
        )
        return [row.user_id for row in rows]


def _deduplicate_posts(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove cross-channel duplicates by fuzzy topic matching.

    Posts are sorted by relevance desc; the first occurrence of a topic is
    kept, later posts with SequenceMatcher ratio > 0.75 are dropped.
    """
    kept: list[dict[str, Any]] = []
    for post in sorted(posts, key=lambda p: p.get("relevance_score", 0), reverse=True):
        topic = post.get("real_topic", "").lower()
        is_dup = any(
            SequenceMatcher(None, topic, k.get("real_topic", "").lower()).ratio() > 0.75
            for k in kept
        )
        if not is_dup:
            kept.append(post)
    return kept


def _build_inline_keyboard(
    button_rows: list[list[dict[str, str]]],
) -> Any:
    """Build a Pyrogram InlineKeyboardMarkup from button dicts."""
    try:
        from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = []
        for row in button_rows:
            keyboard.append(
                [
                    InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"])
                    for btn in row
                ]
            )
        return InlineKeyboardMarkup(keyboard)
    except ImportError:
        return None
