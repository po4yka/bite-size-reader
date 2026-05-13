"""Per-host URL rewriters: ``AcademicPaperRef`` → canonical PDF / landing URL.

These functions are pure URL transformations. They never hit the
network. The orchestrator in ``platform_extractor.py`` uses them to
short-circuit landing-page scraping whenever the host exposes a
deterministic PDF URL pattern.

Hosts that require scraping the landing HTML to find the PDF anchor
(currently ``RESEARCHGATE`` and ``REPEC``) return ``None`` from
``pdf_url_for`` — the orchestrator falls back to anchor discovery for
those.
"""

from __future__ import annotations

from app.adapters.academic.url_patterns import AcademicHost, AcademicPaperRef


def landing_url_for(ref: AcademicPaperRef) -> str | None:
    """Canonical human-facing landing-page URL for the paper.

    Used for user-facing replies, logging context, and as the input to
    the scraper chain when we need to harvest the abstract via HTML.
    Returns None for hosts without a single canonical landing URL.
    """
    if ref.host == AcademicHost.ARXIV:
        return f"https://arxiv.org/abs/{ref.paper_id}{ref.version or ''}"
    if ref.host == AcademicHost.SSRN:
        return f"https://papers.ssrn.com/sol3/papers.cfm?abstract_id={ref.paper_id}"
    if ref.host == AcademicHost.NBER:
        return f"https://www.nber.org/papers/{ref.paper_id}"
    if ref.host == AcademicHost.OSF:
        return f"https://osf.io/{ref.paper_id}/"
    if ref.host == AcademicHost.RESEARCHGATE:
        return f"https://www.researchgate.net/publication/{ref.paper_id}"
    if ref.host == AcademicHost.REPEC:
        return f"https://econpapers.repec.org/RePEc:{ref.paper_id}"
    return None


def pdf_url_for(ref: AcademicPaperRef) -> str | None:
    """Best-effort canonical PDF URL by host-specific URL rewriting.

    Returns None when no deterministic rewrite is known — the caller
    must then scrape the landing page and harvest a PDF ``<a>``
    anchor.
    """
    if ref.host == AcademicHost.ARXIV:
        # arXiv exposes the PDF at /pdf/<id>{vN?}.pdf for every paper.
        # This works without referer cookies and is the cleanest case.
        return f"https://arxiv.org/pdf/{ref.paper_id}{ref.version or ''}.pdf"

    if ref.host == AcademicHost.SSRN:
        # The "Open PDF in Browser" anchor on a papers.cfm page resolves
        # to this Delivery.cfm shape. ``mirid=1`` selects the SSRN-hosted
        # mirror (vs. a publisher mirror that often 403s without referer
        # cookies). Going through Cloudflare is unavoidable; once the
        # patchright stealth path clears the challenge for the landing
        # page, the same session cookies typically carry over to this
        # endpoint.
        return (
            f"https://papers.ssrn.com/sol3/Delivery.cfm/"
            f"SSRN_ID{ref.paper_id}_code0.pdf?abstractid={ref.paper_id}&mirid=1"
        )

    if ref.host == AcademicHost.NBER:
        # NBER's working-paper PDFs live at a deterministic file path;
        # the landing page is just an HTML wrapper over the same id.
        pid = ref.paper_id.lower()
        return f"https://www.nber.org/system/files/working_papers/{pid}/{pid}.pdf"

    if ref.host == AcademicHost.OSF:
        # OSF preprints expose a ``/download`` endpoint that 302s to
        # the underlying file (usually a PDF).
        return f"https://osf.io/{ref.paper_id}/download"

    # RESEARCHGATE and REPEC have no deterministic rewrite — the
    # caller must scrape the landing HTML.
    return None
