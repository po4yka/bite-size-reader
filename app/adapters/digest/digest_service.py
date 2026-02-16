"""Digest service -- orchestrates reader + analyzer + formatter + delivery."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any

from app.db.models import ChannelSubscription, DigestDelivery, _utcnow

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
                await self._send(user_id, "No new posts found for your subscribed channels.")
                result.messages_sent = 1
            except Exception as e:
                result.errors.append(f"Send failed: {e}")
            return result

        # 2. Analyze posts
        try:
            analyzed = await self._analyzer.analyze_posts(posts, correlation_id, lang)
        except Exception as e:
            logger.exception("digest_analysis_failed", extra={"cid": correlation_id})
            result.errors.append(f"Analysis failed: {e}")
            return result

        if not analyzed:
            try:
                await self._send(user_id, "Posts were fetched but analysis produced no results.")
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
                    "All fetched posts were filtered (ads/announcements). No content to digest.",
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
                    "All posts were filtered out (ads, duplicates, or low relevance).",
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
                digest_type=digest_type,
                correlation_id=correlation_id,
                posts_json=post_ids,
            )
        except Exception:
            logger.exception("digest_delivery_persist_failed", extra={"cid": correlation_id})

        logger.info(
            "digest_delivered",
            extra={
                "cid": correlation_id,
                "uid": user_id,
                "posts": result.post_count,
                "channels": result.channel_count,
                "messages": result.messages_sent,
                "type": digest_type,
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
