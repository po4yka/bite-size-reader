"""Academic-paper platform adapter.

Recognizes scholarly-paper URLs (arXiv, SSRN, NBER, OSF preprints,
ResearchGate, RePEc), resolves them to a canonical PDF endpoint, and
extracts abstract + body for downstream summarization. Parallel to
``app/adapters/youtube/``, ``app/adapters/twitter/``, and
``app/adapters/github/``.
"""

from __future__ import annotations

from app.adapters.academic.url_patterns import (
    AcademicHost,
    AcademicPaperRef,
    is_academic_paper_url,
    parse_academic_paper_url,
)

__all__ = [
    "AcademicHost",
    "AcademicPaperRef",
    "is_academic_paper_url",
    "parse_academic_paper_url",
]
