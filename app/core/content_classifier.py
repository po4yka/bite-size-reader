"""Lightweight content classification for model routing.

Classifies extracted content into tiers (DEFAULT, TECHNICAL, SOCIOPOLITICAL)
using URL domain signals and keyword heuristics. No LLM call required.
"""

from __future__ import annotations

import enum
from urllib.parse import urlparse

from app.core.logging_utils import get_logger

logger = get_logger(__name__)

_SCAN_CHARS = 3000
_MIN_KEYWORD_MATCHES = 3


class ContentTier(enum.Enum):
    """Content category for model routing decisions."""

    DEFAULT = "default"
    TECHNICAL = "technical"
    SOCIOPOLITICAL = "sociopolitical"


# ---------------------------------------------------------------------------
# Domain-based signals
# ---------------------------------------------------------------------------

_TECHNICAL_DOMAINS: frozenset[str] = frozenset(
    {
        "arxiv.org",
        "ieee.org",
        "acm.org",
        "dl.acm.org",
        "nature.com",
        "science.org",
        "pnas.org",
        "springer.com",
        "link.springer.com",
        "sciencedirect.com",
        "researchgate.net",
        "pubmed.ncbi.nlm.nih.gov",
        "biorxiv.org",
        "medrxiv.org",
        "github.com",
        "stackoverflow.com",
        "proceedings.neurips.cc",
        "openreview.net",
        "aclanthology.org",
        "journals.aps.org",
        "iopscience.iop.org",
        "docs.python.org",
        "developer.mozilla.org",
        "learn.microsoft.com",
        "cloud.google.com",
        "docs.aws.amazon.com",
    }
)

_SOCIOPOLITICAL_DOMAINS: frozenset[str] = frozenset(
    {
        "politico.com",
        "foreignaffairs.com",
        "foreignpolicy.com",
        "theatlantic.com",
        "newyorker.com",
        "economist.com",
        "nytimes.com",
        "washingtonpost.com",
        "theguardian.com",
        "bbc.com",
        "bbc.co.uk",
        "aljazeera.com",
        "history.com",
        "smithsonianmag.com",
        "brookings.edu",
        "cfr.org",
        "rand.org",
        "lawfaremedia.org",
        "justsecurity.org",
        "cnn.com",
        "reuters.com",
        "apnews.com",
    }
)

# ---------------------------------------------------------------------------
# Keyword-based signals
# ---------------------------------------------------------------------------

_TECHNICAL_KEYWORDS: tuple[str, ...] = (
    "abstract",
    "methodology",
    "doi:",
    "et al.",
    "arxiv",
    "algorithm",
    "implementation",
    "benchmark",
    "theorem",
    "proof",
    "equation",
    "dataset",
    "neural network",
    "regression",
    "hypothesis",
    "p-value",
    "statistically significant",
    "architecture",
    "latency",
    "throughput",
    "complexity",
    "compiler",
    "runtime",
    "kernel",
    "protocol",
    "specification",
    "api",
    "framework",
    "repository",
    "pull request",
    "container",
    "kubernetes",
    "microservice",
    "machine learning",
    "deep learning",
    "transformer",
    "gradient",
    "backpropagation",
    "optimization",
)

_SOCIOPOLITICAL_KEYWORDS: tuple[str, ...] = (
    "geopolitical",
    "diplomacy",
    "sanctions",
    "legislation",
    "congress",
    "parliament",
    "election",
    "democracy",
    "authoritarian",
    "sovereignty",
    "treaty",
    "foreign policy",
    "colonialism",
    "imperialism",
    "civil rights",
    "social justice",
    "inequality",
    "discrimination",
    "immigration",
    "refugee",
    "warfare",
    "military",
    "nuclear",
    "nato",
    "editorial",
    "commentary",
    "historical",
    "century",
    "era",
    "civilization",
    "revolution",
    "independence",
    "political",
    "government",
    "constitution",
    "amendment",
    "bipartisan",
    "liberal",
    "conservative",
)


def _extract_domain(url: str) -> str | None:
    """Extract the registrable domain from a URL."""
    try:
        hostname = urlparse(url).hostname
        if not hostname:
            return None
        # Strip leading www.
        if hostname.startswith("www."):
            hostname = hostname[4:]
        return hostname.lower()
    except Exception:
        return None


def _domain_signal(url: str | None) -> ContentTier | None:
    """Return a tier hint based on URL domain, or None if unknown."""
    if not url:
        return None
    domain = _extract_domain(url)
    if not domain:
        return None
    # Check exact match first, then parent domain (e.g. sub.nature.com -> nature.com)
    for known in _TECHNICAL_DOMAINS:
        if domain == known or domain.endswith("." + known):
            return ContentTier.TECHNICAL
    for known in _SOCIOPOLITICAL_DOMAINS:
        if domain == known or domain.endswith("." + known):
            return ContentTier.SOCIOPOLITICAL
    return None


def _keyword_score(text_lower: str, keywords: tuple[str, ...]) -> int:
    """Count how many keywords appear in the text."""
    return sum(1 for kw in keywords if kw in text_lower)


def _content_signal(content_text: str) -> tuple[int, int]:
    """Return (technical_score, sociopolitical_score) from keyword analysis."""
    sample = content_text[:_SCAN_CHARS].lower()
    tech = _keyword_score(sample, _TECHNICAL_KEYWORDS)
    socio = _keyword_score(sample, _SOCIOPOLITICAL_KEYWORDS)
    return tech, socio


def classify_content(
    content_text: str,
    *,
    url: str | None = None,
) -> ContentTier:
    """Classify content into a tier for model routing.

    Uses a weighted scoring approach:
    - Domain signal (from URL): weight 2
    - Keyword signal (from content): weight 1 per ``_MIN_KEYWORD_MATCHES`` hits

    TECHNICAL wins ties over SOCIOPOLITICAL.
    Returns DEFAULT when signals are insufficient.
    """
    tech_weight = 0
    socio_weight = 0

    # Domain signal (strong hint, weight 2)
    domain_tier = _domain_signal(url)
    if domain_tier == ContentTier.TECHNICAL:
        tech_weight += 2
    elif domain_tier == ContentTier.SOCIOPOLITICAL:
        socio_weight += 2

    # Content keyword signal (weight 1 if >= threshold)
    tech_score, socio_score = _content_signal(content_text)
    if tech_score >= _MIN_KEYWORD_MATCHES:
        tech_weight += 1
    if socio_score >= _MIN_KEYWORD_MATCHES:
        socio_weight += 1

    # Resolve: threshold of 2 to trigger, TECHNICAL wins ties
    if tech_weight >= 2:
        tier = ContentTier.TECHNICAL
    elif socio_weight >= 2 and tech_weight < 2:
        tier = ContentTier.SOCIOPOLITICAL
    elif tech_weight >= 1 and socio_weight == 0:
        tier = ContentTier.TECHNICAL
    elif socio_weight >= 1 and tech_weight == 0:
        tier = ContentTier.SOCIOPOLITICAL
    else:
        tier = ContentTier.DEFAULT

    domain = _extract_domain(url) if url else None
    logger.info(
        "content_tier_classified",
        extra={
            "tier": tier.value,
            "domain_signal": domain_tier.value if domain_tier else None,
            "technical_score": tech_score,
            "sociopolitical_score": socio_score,
            "tech_weight": tech_weight,
            "socio_weight": socio_weight,
            "url_domain": domain,
        },
    )

    return tier
