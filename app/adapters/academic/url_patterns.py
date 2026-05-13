"""Academic-paper URL detection and parsing.

Recognizes the scholarly-paper hosts the bot supports and extracts the
host's canonical paper identifier, so different URL shapes pointing at
the same paper (e.g. ``arxiv.org/abs/X`` and ``arxiv.org/pdf/X.pdf``)
collapse to one identifier for dedupe.

Mirrors the layout of ``app/adapters/github/url_patterns.py`` — pure
parsing functions, no IO, no scraping. The orchestrator in
``platform_extractor.py`` does the network work.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import parse_qs, urlparse


class AcademicHost(StrEnum):
    """Scholarly-paper hosts the academic adapter recognizes."""

    ARXIV = "arxiv"
    SSRN = "ssrn"
    NBER = "nber"
    OSF = "osf"
    RESEARCHGATE = "researchgate"
    REPEC = "repec"


@dataclass(frozen=True, slots=True)
class AcademicPaperRef:
    """Canonical reference to a paper across URL shapes.

    ``paper_id`` is the host's native identifier (arXiv id, SSRN
    abstract id, NBER working-paper number, etc.). ``version``
    captures arXiv's vN suffix when present; we keep it separate from
    ``paper_id`` so dedupe on ``canonical_id`` collapses v1/v2/v3 of
    the same arXiv preprint into one request.
    """

    host: AcademicHost
    paper_id: str
    version: str | None = None

    @property
    def canonical_id(self) -> str:
        """Globally-unique id of the form ``<host>:<paper_id>``.

        Suitable for storing on ``requests.paper_canonical_id`` and for
        dedupe across URL shapes. Excludes ``version`` deliberately.
        """
        return f"{self.host.value}:{self.paper_id}"


# arXiv new-style ids: 2301.00001 (YYMM.NNNNN, 4-5 digit suffix). pdf endpoint
# accepts the same id with an optional .pdf suffix. ``html`` endpoint is the
# rendered preprint introduced in 2024.
_ARXIV_NEW_RE = re.compile(
    r"^https?://(?:www\.)?arxiv\.org/(?:abs|pdf|html)/"
    r"(?P<id>\d{4}\.\d{4,5})(?P<version>v\d+)?(?:\.pdf)?/?$",
    re.IGNORECASE,
)
# arXiv legacy ids: hep-th/0102003, cs.AI/0102003, etc. (pre-April 2007).
_ARXIV_OLD_RE = re.compile(
    r"^https?://(?:www\.)?arxiv\.org/(?:abs|pdf|html)/"
    r"(?P<id>[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?P<version>v\d+)?(?:\.pdf)?/?$",
    re.IGNORECASE,
)

_SSRN_HOSTS = frozenset({"papers.ssrn.com", "ssrn.com", "www.ssrn.com"})
_SSRN_ABSTRACT_ID_KEYS = ("abstract_id", "abstractid", "abstractId")

_NBER_URL_RE = re.compile(
    r"^https?://(?:www\.)?nber\.org/papers/(?P<id>[a-z]\d+)(?:\.pdf)?/?$",
    re.IGNORECASE,
)

# osf preprint paths: /preprints/<server>/<id>; some short shapes use /<id> directly.
_OSF_PREPRINT_RE = re.compile(
    r"^https?://(?:www\.)?osf\.io/preprints/[^/]+/(?P<id>[a-z0-9]{4,8})/?$",
    re.IGNORECASE,
)

_RESEARCHGATE_URL_RE = re.compile(
    r"^https?://(?:www\.)?researchgate\.net/publication/(?P<id>\d+)(?:[/_].*)?$",
    re.IGNORECASE,
)

_REPEC_URL_RE = re.compile(
    r"^https?://(?:www\.)?econpapers\.repec\.org/RePEc:(?P<id>[^?#]+?)/?$",
    re.IGNORECASE,
)


def parse_academic_paper_url(url: str) -> AcademicPaperRef | None:
    """Identify the host + canonical paper id, or return None.

    Tries each host's pattern in order; returns the first match. Order
    is roughly "most-likely-to-match first" but the patterns are
    disjoint by domain so ordering is not load-bearing for
    correctness.
    """
    if not url:
        return None
    url = url.strip()

    # arXiv (try new-style first; old-style ids contain a slash so they
    # won't match the new-style pattern anyway).
    if (m := _ARXIV_NEW_RE.match(url)) or (m := _ARXIV_OLD_RE.match(url)):
        return AcademicPaperRef(
            host=AcademicHost.ARXIV,
            paper_id=m.group("id"),
            version=m.group("version"),
        )

    # SSRN — abstract_id lives in the query string for both papers.cfm
    # and Delivery.cfm endpoints, so the cleanest detector is host-match
    # plus parse_qs.
    parsed = urlparse(url)
    if parsed.netloc.lower() in _SSRN_HOSTS:
        qs = parse_qs(parsed.query)
        for key in _SSRN_ABSTRACT_ID_KEYS:
            value = qs.get(key)
            if value and value[0].isdigit():
                return AcademicPaperRef(host=AcademicHost.SSRN, paper_id=value[0])

    if m := _NBER_URL_RE.match(url):
        return AcademicPaperRef(host=AcademicHost.NBER, paper_id=m.group("id").lower())

    if m := _OSF_PREPRINT_RE.match(url):
        return AcademicPaperRef(host=AcademicHost.OSF, paper_id=m.group("id").lower())

    if m := _RESEARCHGATE_URL_RE.match(url):
        return AcademicPaperRef(host=AcademicHost.RESEARCHGATE, paper_id=m.group("id"))

    if m := _REPEC_URL_RE.match(url):
        return AcademicPaperRef(host=AcademicHost.REPEC, paper_id=m.group("id"))

    return None


def is_academic_paper_url(url: str) -> bool:
    """True iff ``parse_academic_paper_url`` would identify the URL."""
    return parse_academic_paper_url(url) is not None
