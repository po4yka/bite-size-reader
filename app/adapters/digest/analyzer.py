"""Digest analyzer -- lightweight LLM analysis for channel posts."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core.json_utils import extract_json
from app.db.models import ChannelPost, ChannelPostAnalysis, _utcnow

if TYPE_CHECKING:
    from app.adapters.llm.protocol import LLMClientProtocol
    from app.config import AppConfig

logger = logging.getLogger(__name__)

PROMPT_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

VALID_CONTENT_TYPES = {"news", "tutorial", "opinion", "announcement", "other"}


class DigestAnalyzer:
    """Runs lightweight LLM analysis on channel posts with concurrency control."""

    def __init__(self, cfg: AppConfig, llm_client: LLMClientProtocol) -> None:
        self._cfg = cfg
        self._llm = llm_client
        self._semaphore = asyncio.Semaphore(cfg.digest.concurrency)

    async def analyze_posts(
        self,
        posts: list[dict[str, Any]],
        correlation_id: str,
        lang: str = "en",
    ) -> list[dict[str, Any]]:
        """Analyze a batch of posts concurrently with semaphore control.

        Args:
            posts: List of post dicts from ChannelReader.
            correlation_id: Correlation ID for tracing.
            lang: Language for prompt selection (en/ru).

        Returns:
            List of analysis result dicts.
        """
        tasks = [self._analyze_single(post, correlation_id, lang) for post in posts]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        analyzed: list[dict[str, Any]] = []
        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                logger.warning(
                    "digest_analysis_single_failed",
                    extra={
                        "cid": correlation_id,
                        "post_url": posts[i].get("url"),
                        "error": str(result),
                    },
                )
                continue
            if result is not None and isinstance(result, dict):
                analyzed.append(result)

        logger.info(
            "digest_analysis_batch_complete",
            extra={
                "cid": correlation_id,
                "total": len(posts),
                "analyzed": len(analyzed),
            },
        )
        return analyzed

    async def _analyze_single(
        self,
        post: dict[str, Any],
        correlation_id: str,
        lang: str,
    ) -> dict[str, Any] | None:
        """Analyze a single post under the concurrency semaphore."""
        async with self._semaphore:
            prompt_template = self._load_prompt(lang)
            user_prompt = prompt_template.replace("{post_text}", post["text"][:4000])

            messages: list[dict[str, Any]] = [
                {"role": "user", "content": user_prompt},
            ]

            result = await self._llm.chat(
                messages,
                temperature=0.1,
                max_tokens=500,
            )

            if result.status != "ok" or result.error_text:
                logger.warning(
                    "digest_llm_error",
                    extra={"cid": correlation_id, "error": result.error_text},
                )
                return None

            # Parse JSON response
            raw_text = result.response_text or ""
            parsed = extract_json(raw_text)

            if parsed is None or not isinstance(parsed, dict):
                logger.warning(
                    "digest_analysis_parse_failed",
                    extra={"cid": correlation_id, "raw": raw_text[:200]},
                )
                return None

            # Validate required fields
            real_topic = str(parsed.get("real_topic", "")).strip()
            tldr = str(parsed.get("tldr", "")).strip()
            if not real_topic or not tldr:
                logger.warning(
                    "digest_analysis_missing_fields",
                    extra={"cid": correlation_id},
                )
                return None

            key_insights = parsed.get("key_insights")
            if not isinstance(key_insights, list):
                key_insights = []

            relevance_score = parsed.get("relevance_score", 0.5)
            try:
                relevance_score = max(0.0, min(1.0, float(relevance_score)))
            except (TypeError, ValueError):
                relevance_score = 0.5

            content_type = str(parsed.get("content_type", "other")).strip().lower()
            if content_type not in VALID_CONTENT_TYPES:
                content_type = "other"

            # Persist to DB
            channel_post = (
                ChannelPost.select()
                .where(
                    ChannelPost.channel == post.get("_channel_id"),
                    ChannelPost.message_id == post["message_id"],
                )
                .first()
            )

            if channel_post:
                ChannelPostAnalysis.get_or_create(
                    post=channel_post,
                    defaults={
                        "real_topic": real_topic,
                        "tldr": tldr,
                        "key_insights": key_insights,
                        "relevance_score": relevance_score,
                        "content_type": content_type,
                    },
                )
                ChannelPost.update(analyzed_at=_utcnow()).where(
                    ChannelPost.id == channel_post.id
                ).execute()

            return {
                **post,
                "real_topic": real_topic,
                "tldr": tldr,
                "key_insights": key_insights,
                "relevance_score": relevance_score,
                "content_type": content_type,
            }

    @staticmethod
    def _load_prompt(lang: str) -> str:
        """Load the digest analysis prompt for the given language."""
        safe_lang = "ru" if lang.startswith("ru") else "en"
        path = PROMPT_DIR / f"digest_analysis_{safe_lang}.txt"
        try:
            return path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            # Fallback to English
            fallback = PROMPT_DIR / "digest_analysis_en.txt"
            return fallback.read_text(encoding="utf-8").strip()
