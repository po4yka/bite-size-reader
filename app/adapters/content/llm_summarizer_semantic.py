"""Semantic helpers for LLM summarization."""

from __future__ import annotations

import asyncio
import logging
import re
from collections import Counter
from typing import Any

from app.core.async_utils import raise_if_cancelled
from app.core.summary_contract import _cap_text, _extract_keywords_tfidf, _normalize_whitespace

logger = logging.getLogger(__name__)

# Simple stop words for keyword extraction
_SIMPLE_KEYWORD_STOP_WORDS = {
    "and",
    "the",
    "with",
    "from",
    "that",
    "this",
    "they",
    "been",
    "have",
    "were",
    "their",
    "will",
    "some",
    "который",
    "через",
    "между",
    "после",
    "перед",
    "было",
    "были",
    "есть",
    "будет",
    "этого",
    "чтобы",
}


class LLMSemanticHelper:
    """Build semantic fields for retrieval and follow-up workflows."""

    async def enrich_with_rag_fields(
        self,
        summary: dict[str, Any],
        *,
        content_text: str,
        chosen_lang: str | None,
        req_id: int,
    ) -> dict[str, Any]:
        """Attach RAG-optimized fields derived from content and summary."""
        if not isinstance(summary, dict):
            return summary

        lang = chosen_lang or summary.get("language")
        summary["language"] = lang
        article_id = summary.get("article_id") or str(req_id)
        summary["article_id"] = str(article_id) if article_id else None

        topics = [
            str(t).strip().lstrip("#")
            for t in summary.get("topic_tags", [])
            if isinstance(t, str) and str(t).strip()
        ]

        base_text = " ".join(
            [
                summary.get("summary_1000") or "",
                summary.get("summary_250") or "",
                summary.get("tldr") or "",
            ]
        )

        if not summary.get("semantic_boosters"):
            summary["semantic_boosters"] = self._generate_semantic_boosters(base_text, summary)
        else:
            summary["semantic_boosters"] = summary.get("semantic_boosters", [])[:15]

        if (
            not summary.get("query_expansion_keywords")
            or len(summary["query_expansion_keywords"]) < 20
        ):
            summary["query_expansion_keywords"] = await self._generate_query_expansion_keywords(
                summary, content_text or base_text
            )
        else:
            summary["query_expansion_keywords"] = summary.get("query_expansion_keywords", [])[:30]

        if not summary.get("semantic_chunks"):
            summary["semantic_chunks"] = self._build_semantic_chunks(
                content_text,
                topics=topics,
                article_id=summary.get("article_id"),
                language=lang,
            )

        return summary

    async def _extract_keywords_tfidf_async(self, content_text: str, topn: int) -> list[str]:
        if not content_text.strip():
            return []
        try:
            return await asyncio.to_thread(_extract_keywords_tfidf, content_text, topn=topn)
        except Exception as exc:  # pragma: no cover - defensive
            raise_if_cancelled(exc)
            logger.warning("tfidf_async_failed", extra={"error": str(exc)})
            return []

    def _extract_keywords_simple(self, text: str, topn: int = 8) -> list[str]:
        if not text or not text.strip():
            return []
        words = re.findall(r"\b\w+\b", text.lower())
        candidates: list[str] = []
        for word in words:
            if len(word) < 4 or word in _SIMPLE_KEYWORD_STOP_WORDS:
                continue
            if word.isdigit():
                continue
            if not any(ch.isalpha() for ch in word):
                continue
            candidates.append(word)
        if not candidates:
            return []
        counts = Counter(candidates)
        return [term for term, _ in counts.most_common(topn)]

    async def _generate_query_expansion_keywords(
        self, summary: dict[str, Any], content_text: str
    ) -> list[str]:
        seeds: list[str] = []
        for source in ("query_expansion_keywords", "seo_keywords", "key_ideas"):
            values = summary.get(source) or []
            if isinstance(values, list):
                seeds.extend([str(v).strip() for v in values if str(v).strip()])

        topic_tags = summary.get("topic_tags") or []
        seeds.extend([str(t).strip().lstrip("#") for t in topic_tags if str(t).strip()])

        tfidf_source = (content_text or "")[:20000]
        tfidf_terms = await self._extract_keywords_tfidf_async(tfidf_source, topn=40)
        seeds.extend(tfidf_terms)

        deduped: list[str] = []
        seen: set[str] = set()
        for term in seeds:
            key = term.lower()
            if key and key not in seen:
                seen.add(key)
                deduped.append(term)

        if len(deduped) < 20:
            for term in tfidf_terms:
                if term not in deduped:
                    deduped.append(term)
                if len(deduped) >= 20:
                    break

        return deduped[:30]

    def _generate_semantic_boosters(self, base_text: str, summary: dict[str, Any]) -> list[str]:
        boosters: list[str] = []
        from_summary = summary.get("semantic_boosters") or []
        if isinstance(from_summary, list):
            boosters.extend([_cap_text(str(b), 320) for b in from_summary if str(b).strip()])

        sentences = re.split(r"(?<=[.!?])\s+", _normalize_whitespace(base_text))
        for sentence in sentences:
            if len(boosters) >= 15:
                break
            if sentence and sentence not in boosters and len(sentence) > 20:
                boosters.append(_cap_text(sentence, 320))

        return boosters[:15]

    def _build_semantic_chunks(
        self,
        content_text: str,
        *,
        topics: list[str],
        article_id: str | None,
        language: str | None,
        target_words: int = 150,
    ) -> list[dict[str, Any]]:
        if not content_text or not content_text.strip():
            return []

        words = content_text.split()
        chunks: list[dict[str, Any]] = []
        start = 0

        while start < len(words):
            end = min(len(words), start + target_words)
            # Ensure minimum length by expanding to 100 words when near boundary
            if end - start < 100 and end < len(words):
                end = min(len(words), start + 100)

            chunk_text = " ".join(words[start:end]).strip()
            if not chunk_text:
                break

            local_summary = self._extract_local_summary(chunk_text)
            local_keywords = self._extract_keywords_simple(chunk_text, topn=8)

            chunks.append(
                {
                    "article_id": article_id,
                    "section": None,
                    "language": language,
                    "topics": topics,
                    "text": chunk_text,
                    "local_summary": local_summary,
                    "local_keywords": local_keywords,
                }
            )

            start = end

        return chunks

    def _extract_local_summary(self, chunk_text: str) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", chunk_text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences:
            return _cap_text(chunk_text, 320)
        selected = " ".join(sentences[:2])
        return _cap_text(selected, 320)
