"""Quality heuristics for extracted Twitter article content."""

from __future__ import annotations

import re


def is_low_quality_article_content(content: str) -> bool:
    """Detect login walls and UI chrome scraped instead of article content."""
    normalized = re.sub(r"\s+", " ", content).strip().lower()
    if len(normalized) < 60:
        return True

    login_wall_phrases = (
        "log in to x",
        "sign in to x",
        "sign up for x",
        "join x today",
        "by signing up, you agree",
        "terms of service",
        "privacy policy",
    )
    if any(phrase in normalized for phrase in login_wall_phrases) and len(normalized) < 240:
        return True

    tokens = re.findall(r"[a-z0-9']+", normalized)
    if not tokens:
        return True

    ui_terms = {"log", "login", "sign", "signup", "signin", "cookie", "cookies", "privacy"}
    ui_ratio = sum(1 for token in tokens if token in ui_terms) / len(tokens)
    return len(tokens) < 80 and ui_ratio >= 0.18
