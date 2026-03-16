"""Analytics helpers for API search insights."""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime
from typing import Any

from app.application.services.topic_search_utils import ensure_mapping
from app.core.logging_utils import get_logger

logger = get_logger(__name__)


def period_tag_counts(
    rows: list[tuple[datetime, list[str]]], start: datetime, end: datetime
) -> Counter[str]:
    counts: Counter[str] = Counter()
    for created_at, tags in rows:
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError:
                logger.debug(
                    "period_tag_counts_invalid_created_at",
                    extra={"created_at": created_at},
                )
                continue
        if created_at < start or created_at >= end:
            continue
        for tag in tags:
            normalized = str(tag).strip().lower()
            if normalized:
                counts[normalized] += 1
    return counts


def compute_search_insights_payload(
    *,
    rows: list[dict[str, Any]],
    now: datetime,
    current_start: datetime,
    previous_start: datetime,
    days: int,
    limit: int,
) -> dict[str, Any]:
    tag_rows: list[tuple[datetime, list[str]]] = []
    entity_counts: Counter[str] = Counter()
    domain_counts: Counter[str] = Counter()
    lang_counts: Counter[str] = Counter()
    keyword_counts: Counter[str] = Counter()
    tag_counts_total: Counter[str] = Counter()
    total_articles = 0

    for row in rows:
        payload = ensure_mapping(row.get("json_payload"))
        metadata = ensure_mapping(payload.get("metadata"))
        entities = ensure_mapping(payload.get("entities"))
        request_data = ensure_mapping(row.get("request"))
        created_at = request_data.get("created_at")
        if created_at is None:
            continue
        total_articles += 1

        tags = [str(t).strip().lower() for t in (payload.get("topic_tags") or []) if str(t).strip()]
        tag_rows.append((created_at, tags))
        tag_counts_total.update(tags)

        domain = str(metadata.get("domain") or "").strip().lower()
        if domain:
            domain_counts[domain] += 1
        lang = str(row.get("lang") or "unknown").strip().lower()
        lang_counts[lang] += 1

        for bucket in ("people", "organizations", "locations"):
            values = entities.get(bucket) or []
            for value in values[:40]:
                normalized = str(value).strip()
                if normalized:
                    entity_counts[normalized] += 1
        for kw in payload.get("seo_keywords") or []:
            normalized_kw = str(kw).strip().lower()
            if normalized_kw:
                keyword_counts[normalized_kw] += 1

    current_tags = period_tag_counts(tag_rows, current_start, now)
    previous_tags = period_tag_counts(tag_rows, previous_start, current_start)
    trending_topics: list[dict[str, Any]] = []
    for tag, count in current_tags.most_common(limit):
        prev = previous_tags.get(tag, 0)
        trend_delta = count - prev
        trend_score = round((count - prev) / prev, 3) if prev > 0 else 1.0 if count > 0 else 0.0
        trending_topics.append(
            {
                "tag": tag,
                "count": count,
                "prev_count": prev,
                "trend_delta": trend_delta,
                "trend_score": trend_score,
            }
        )

    rising_entities = [
        {"entity": entity, "count": count} for entity, count in entity_counts.most_common(limit)
    ]
    source_diversity = {
        "unique_domains": len(domain_counts),
        "top_domains": [
            {"domain": domain, "count": count} for domain, count in domain_counts.most_common(limit)
        ],
    }
    if total_articles > 0:
        entropy = 0.0
        for count in domain_counts.values():
            probability = count / total_articles
            if probability > 0:
                entropy -= probability * math.log2(probability)
        source_diversity["shannon_entropy"] = round(entropy, 4)
    else:
        source_diversity["shannon_entropy"] = 0.0

    language_mix = {
        "total": total_articles,
        "languages": [
            {
                "language": lang,
                "count": count,
                "ratio": round((count / total_articles), 4) if total_articles else 0.0,
            }
            for lang, count in lang_counts.most_common(limit)
        ],
    }
    tag_tokens = {tag.lstrip("#") for tag in tag_counts_total}
    gaps: list[dict[str, Any]] = []
    for keyword, count in keyword_counts.most_common(limit * 4):
        if keyword in tag_tokens or count < 2:
            continue
        gaps.append(
            {
                "term": keyword,
                "mentions": count,
                "tag_coverage": 0,
                "gap_score": round(count / max(1, total_articles), 4),
            }
        )
        if len(gaps) >= limit:
            break

    return {
        "period_days": days,
        "window": {
            "start": current_start.isoformat().replace("+00:00", "Z"),
            "end": now.isoformat().replace("+00:00", "Z"),
        },
        "topic_trends": trending_topics,
        "rising_entities": rising_entities,
        "source_diversity": source_diversity,
        "language_mix": language_mix,
        "coverage_gaps": gaps,
    }
