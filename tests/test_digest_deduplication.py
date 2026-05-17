"""Tests for digest post deduplication helpers."""

from __future__ import annotations

from app.adapters.digest.digest_service import _deduplicate_posts


def _post(topic: str, score: float) -> dict[str, object]:
    return {"real_topic": topic, "relevance_score": score}


def test_deduplicate_posts_preserves_pairwise_behavior_for_small_inputs() -> None:
    posts = [
        _post("Major Python release lands today", 0.9),
        _post("Major Python release landed today", 0.8),
        _post("Database migration guide", 0.7),
    ]

    deduplicated = _deduplicate_posts(posts)

    assert [post["real_topic"] for post in deduplicated] == [
        "Major Python release lands today",
        "Database migration guide",
    ]


def test_deduplicate_posts_uses_buckets_for_large_inputs() -> None:
    posts = [_post(f"Unique topic number {index}", 0.5) for index in range(70)]
    posts.extend(
        [
            _post("Alpha release changes database indexes", 1.0),
            _post("Alpha release changed database indexes", 0.9),
        ]
    )

    deduplicated = _deduplicate_posts(posts)
    topics = [post["real_topic"] for post in deduplicated]

    assert "Alpha release changes database indexes" in topics
    assert "Alpha release changed database indexes" not in topics
