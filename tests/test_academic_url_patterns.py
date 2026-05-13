"""Unit tests for academic-paper URL detection and resolution.

Pure parsing tests — no network, no fixtures, no DB. The orchestrator's
end-to-end behavior is covered separately in
``test_academic_platform_extractor.py``.
"""

from __future__ import annotations

import pytest

from app.adapters.academic.resolvers import landing_url_for, pdf_url_for
from app.adapters.academic.url_patterns import (
    AcademicHost,
    AcademicPaperRef,
    is_academic_paper_url,
    parse_academic_paper_url,
)


# ---------------------------------------------------------------------------
# arXiv
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "expected_id", "expected_version"),
    [
        ("https://arxiv.org/abs/2301.00001", "2301.00001", None),
        ("https://arxiv.org/abs/2301.00001v2", "2301.00001", "v2"),
        ("https://arxiv.org/pdf/2301.00001.pdf", "2301.00001", None),
        ("https://arxiv.org/pdf/2301.00001v3.pdf", "2301.00001", "v3"),
        ("http://www.arxiv.org/abs/2301.12345", "2301.12345", None),
        ("https://arxiv.org/html/2401.99999", "2401.99999", None),
        ("https://arxiv.org/abs/2412.00123", "2412.00123", None),
        # 5-digit suffix (post-2015 arXiv id format)
        ("https://arxiv.org/abs/2301.12345/", "2301.12345", None),
    ],
)
def test_arxiv_new_style(url: str, expected_id: str, expected_version: str | None) -> None:
    ref = parse_academic_paper_url(url)
    assert ref is not None
    assert ref.host == AcademicHost.ARXIV
    assert ref.paper_id == expected_id
    assert ref.version == expected_version


def test_arxiv_old_style_id_preserved() -> None:
    """Legacy arXiv ids contain a slash (e.g. cs.AI/0102003) — must parse."""
    ref = parse_academic_paper_url("https://arxiv.org/abs/cs.AI/0102003")
    assert ref is not None
    assert ref.host == AcademicHost.ARXIV
    assert ref.paper_id == "cs.AI/0102003"


def test_arxiv_abs_and_pdf_share_canonical_id() -> None:
    """Dedupe contract: ``/abs/X`` and ``/pdf/X.pdf`` must collapse."""
    a = parse_academic_paper_url("https://arxiv.org/abs/2301.00001")
    b = parse_academic_paper_url("https://arxiv.org/pdf/2301.00001.pdf")
    assert a is not None
    assert b is not None
    assert a.canonical_id == b.canonical_id == "arxiv:2301.00001"


def test_arxiv_versions_share_canonical_id() -> None:
    """v1 and v2 of the same preprint dedupe to the same canonical id."""
    v1 = parse_academic_paper_url("https://arxiv.org/abs/2301.00001v1")
    v2 = parse_academic_paper_url("https://arxiv.org/abs/2301.00001v2")
    assert v1 is not None
    assert v2 is not None
    assert v1.canonical_id == v2.canonical_id


def test_arxiv_pdf_url_rewrite() -> None:
    ref = AcademicPaperRef(host=AcademicHost.ARXIV, paper_id="2301.00001")
    assert pdf_url_for(ref) == "https://arxiv.org/pdf/2301.00001.pdf"
    ref_v2 = AcademicPaperRef(host=AcademicHost.ARXIV, paper_id="2301.00001", version="v2")
    assert pdf_url_for(ref_v2) == "https://arxiv.org/pdf/2301.00001v2.pdf"


def test_arxiv_landing_url() -> None:
    ref = AcademicPaperRef(host=AcademicHost.ARXIV, paper_id="2301.00001")
    assert landing_url_for(ref) == "https://arxiv.org/abs/2301.00001"


# ---------------------------------------------------------------------------
# SSRN — including the exact URL that produced correlation id bacbd8fa7639
# ---------------------------------------------------------------------------


def test_ssrn_papers_cfm_url() -> None:
    ref = parse_academic_paper_url(
        "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6531478"
    )
    assert ref is not None
    assert ref.host == AcademicHost.SSRN
    assert ref.paper_id == "6531478"
    assert ref.canonical_id == "ssrn:6531478"


def test_ssrn_delivery_url_dedupes_with_papers_cfm() -> None:
    """The Delivery.cfm endpoint exposes ``abstractid``; both URL shapes
    pointing at the same paper must dedupe to a single canonical id."""
    landing = parse_academic_paper_url(
        "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6531478"
    )
    delivery = parse_academic_paper_url(
        "https://papers.ssrn.com/sol3/Delivery.cfm/"
        "SSRN_ID6531478_code0.pdf?abstractid=6531478&mirid=1"
    )
    assert landing is not None
    assert delivery is not None
    assert landing.canonical_id == delivery.canonical_id


def test_ssrn_pdf_url_rewrite_includes_abstractid() -> None:
    ref = AcademicPaperRef(host=AcademicHost.SSRN, paper_id="6531478")
    pdf = pdf_url_for(ref)
    assert pdf is not None
    assert "abstractid=6531478" in pdf
    assert "Delivery.cfm" in pdf
    assert "mirid=1" in pdf


# ---------------------------------------------------------------------------
# NBER
# ---------------------------------------------------------------------------


def test_nber_working_paper_url() -> None:
    ref = parse_academic_paper_url("https://www.nber.org/papers/w12345")
    assert ref is not None
    assert ref.host == AcademicHost.NBER
    assert ref.paper_id == "w12345"


def test_nber_pdf_url_rewrite() -> None:
    ref = AcademicPaperRef(host=AcademicHost.NBER, paper_id="w12345")
    assert (
        pdf_url_for(ref)
        == "https://www.nber.org/system/files/working_papers/w12345/w12345.pdf"
    )


# ---------------------------------------------------------------------------
# OSF preprints
# ---------------------------------------------------------------------------


def test_osf_preprint_url() -> None:
    ref = parse_academic_paper_url("https://osf.io/preprints/socarxiv/abc12")
    assert ref is not None
    assert ref.host == AcademicHost.OSF
    assert ref.paper_id == "abc12"


def test_osf_pdf_url_rewrite() -> None:
    ref = AcademicPaperRef(host=AcademicHost.OSF, paper_id="abc12")
    assert pdf_url_for(ref) == "https://osf.io/abc12/download"


# ---------------------------------------------------------------------------
# ResearchGate, RePEc — no deterministic PDF rewrite
# ---------------------------------------------------------------------------


def test_researchgate_url_parsed() -> None:
    ref = parse_academic_paper_url(
        "https://www.researchgate.net/publication/12345678_Some_Paper_Title"
    )
    assert ref is not None
    assert ref.host == AcademicHost.RESEARCHGATE
    assert ref.paper_id == "12345678"


def test_researchgate_has_no_deterministic_pdf_rewrite() -> None:
    """Caller must fall back to scraping the landing HTML for an anchor."""
    ref = AcademicPaperRef(host=AcademicHost.RESEARCHGATE, paper_id="12345678")
    assert pdf_url_for(ref) is None


def test_repec_url_parsed() -> None:
    ref = parse_academic_paper_url(
        "https://econpapers.repec.org/RePEc:nbr:nberwo:12345"
    )
    assert ref is not None
    assert ref.host == AcademicHost.REPEC
    assert pdf_url_for(ref) is None


# ---------------------------------------------------------------------------
# Non-academic URLs must be rejected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/article",
        "https://habr.com/ru/articles/1032228/",
        "https://github.com/anthropics/claude-code",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://twitter.com/user/status/123",
        "https://arxiv.org/",  # root, no id
        "https://arxiv.org/abs/",  # no id
        "https://papers.ssrn.com/",  # no abstract_id
        "https://www.nber.org/research/",  # not a /papers/ path
        "",
        "not a url",
    ],
)
def test_non_academic_urls_rejected(url: str) -> None:
    assert parse_academic_paper_url(url) is None
    assert is_academic_paper_url(url) is False


# ---------------------------------------------------------------------------
# Canonical id shape
# ---------------------------------------------------------------------------


def test_canonical_id_format() -> None:
    ref = AcademicPaperRef(host=AcademicHost.ARXIV, paper_id="2301.00001")
    assert ref.canonical_id == "arxiv:2301.00001"


def test_canonical_id_excludes_version() -> None:
    """Dedupe must not split v1 and v2 of the same arXiv preprint."""
    v1 = AcademicPaperRef(host=AcademicHost.ARXIV, paper_id="2301.00001", version="v1")
    v2 = AcademicPaperRef(host=AcademicHost.ARXIV, paper_id="2301.00001", version="v2")
    assert v1.canonical_id == v2.canonical_id
