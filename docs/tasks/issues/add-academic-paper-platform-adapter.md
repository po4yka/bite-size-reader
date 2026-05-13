---
title: Add academic-paper platform adapter (SSRN, arXiv, NBER, OSF preprints)
status: doing
area: content
priority: medium
owner: TBD
blocks: []
blocked_by: []
created: 2026-05-13
updated: 2026-05-13
---

- [ ] #task Add academic-paper platform adapter (SSRN, arXiv, NBER, OSF preprints) #repo/ratatoskr #area/content #status/doing 🔼

## Problem

Scholarly-paper landing pages (SSRN, arXiv, NBER, OSF, RePEc, ResearchGate) have a structurally different content model from the articles, videos, and forwarded posts the bot already handles:

- The HTML landing page carries only **metadata + abstract** (title, authors, JEL/MSC tags, ~300-word abstract).
- The **actual content lives in a separately-linked PDF** (typically 10–60 pages).
- Many of these hosts (SSRN, ResearchGate) sit behind **Cloudflare anti-bot**, so the generic scraper chain often comes back with `insufficient_useful_content:empty_after_cleaning (chars=0, words=0)` (cf. correlation id `bacbd8fa7639`, request 1301, May 2026).

Today the chain treats these URLs as ordinary articles, the abstract usually doesn't survive cleaning, and even when it does, the user gets a summary of a 300-word abstract instead of a 16-page paper.

## Proposed approach

Stand up a dedicated `app/adapters/academic/` platform adapter, structured the same way as `app/adapters/youtube/` and `app/adapters/twitter/`:

1. **`url_patterns.py`** — recognize `arxiv.org/abs/<id>`, `arxiv.org/pdf/<id>`, `papers.ssrn.com/sol3/papers.cfm?abstract_id=<id>`, `papers.ssrn.com/sol3/Delivery.cfm/...`, `nber.org/papers/<id>`, `osf.io/preprints/...`, `econpapers.repec.org/...`, `www.researchgate.net/publication/<id>`. Each pattern returns a host enum + canonical paper id.
2. **`<host>_resolver.py`** (one per host) — map landing URL → canonical PDF URL by URL rewriting first, falling back to HTML anchor discovery when rewriting isn't enough:
    - **arXiv**: trivial `/abs/X` → `/pdf/X.pdf` (or `…v2.pdf`); no scrape needed.
    - **SSRN**: from `abstract_id=X`, attempt the `Delivery.cfm/<X>.pdf?abstractid=X&mirid=1` shape that the page's "Open PDF in Browser" button resolves to; falls back to scraping the landing HTML (post-Cloudflare, via patchright) to harvest the actual anchor.
    - **NBER**: `nber.org/papers/<id>` → `nber.org/system/files/working_papers/<id>/<id>.pdf` rewrite.
    - **OSF / ResearchGate**: anchor discovery only.
3. **`paper_extractor.py`** — orchestrator:
    1. Fetch landing HTML via the existing scraper chain (so we reuse stealth / patchright / Cloudflare clearance for hosts that need it). Persist as a `crawl_result` so the audit trail matches the rest of the system.
    2. Pull metadata (title, authors, abstract, DOI when present) from the HTML using host-specific selectors. Cache the abstract.
    3. Resolve the PDF URL via the host resolver.
    4. Download the PDF (size cap — see open question below).
    5. Extract text via the existing `pymupdf` path (already in the `attachment` extra; see `app/adapters/attachment/`). Strip references/bibliography section if structurally identifiable.
    6. Combine: feed the LLM `[abstract] + [body]` (abstract first — gives the model an author-authored TL;DR before the long form).
4. **Routing** — intercept in `app/adapters/content/url_processor.py` (or the URL flow that already dispatches youtube/twitter), before the generic scraper chain. The interception predicate is "URL pattern matches a known academic host."
5. **Persistence** — store both crawls (HTML + PDF) as separate `crawl_results` rows linked to the same `request_id`, so correlation-id tracing keeps working.

## Resolved decisions (2026-05-13 interview)

- **PDF size cap:** *no cap* — let the existing chunker in `app/agents/summarization_agent.py` handle long papers. Watch token cost in observability after rollout; revisit if a single request blows the budget.
- **SSRN paywall:** try every scraper / bypass path first (now that patchright is wired up), and *only after* all bypass attempts fail, return an abstract-only summary with an explicit `[PDF unavailable: paywall]` note in the user-facing reply. Never return a generic extraction-failure when the abstract is in hand.
- **Paper dedupe:** add a nullable `paper_canonical_id` column on `requests` (e.g. `arxiv:2301.00001`, `ssrn:6531478`, `doi:10.xxxx/...`). Dual-key dedupe: prefer `(host, paper_id)` when present, fall back to the existing `dedupe_hash` over the normalized URL. Two URLs pointing at the same paper collapse to one request.
- **Mobile API surface:** standard summaries feed with a `source_type='academic_paper'` discriminator on the summary row. No dedicated Papers tab or citation export in this slice — deferred to a follow-up issue if usage data justifies it.
- **References-section stripping:** *deferred*. Ship without stripping; revisit only if measured token usage on real papers proves limiting. The heuristic is host-specific and brittle enough that "ship the simple thing first" wins.
- **Generic `*.pdf` URL support:** *out of scope* for this issue. Capture as a follow-up: any URL whose content-type is `application/pdf` or whose path ends in `.pdf` could flow through the same PDF-extraction pipeline. Defer until the academic slice has shipped and we know the pymupdf path is stable on the Pi.

## Files to touch

- `app/adapters/academic/__init__.py` — new package
- `app/adapters/academic/url_patterns.py` — host detection + canonical id parser
- `app/adapters/academic/resolvers/{arxiv,ssrn,nber,osf,researchgate}.py` — per-host URL→PDF mapping
- `app/adapters/academic/paper_extractor.py` — orchestrator
- `app/adapters/content/url_processor.py` — wire in the academic interceptor before the generic chain
- `app/adapters/content/url_flow_models.py` — extend `URLFlowContext` with paper-specific fields (paper_id, host, abstract_text) if needed for chunking
- `app/core/summary_schema.py` / `app/core/summary_contract.py` — confirm `source_type` enum already covers `academic_paper`; extend if not
- `app/db/models/core.py` — possibly extend `Request` with a `paper_canonical_id` column (or new `papers` table) — pending the dedupe open question
- `app/prompts/summary_system_en.txt` / `summary_system_ru.txt` — add a short "if the input is an academic paper (abstract + body), structure key_ideas around the paper's claims, evidence, and limitations" instruction
- `tests/test_academic_url_patterns.py` (new) — URL parsing unit tests
- `tests/test_academic_pdf_extraction.py` (new) — fixture-backed integration test using a small public arXiv PDF
- `docs/SPEC.md` — document the new content source under the URL-flow section
- `CLAUDE.md` — add `app/adapters/academic/` to the directory structure block under "Architecture Overview"

## Acceptance criteria

- [ ] arXiv URL (e.g. `https://arxiv.org/abs/2301.00001`) returns a summary whose body reflects content beyond the abstract (token count of input materially exceeds abstract length).
- [ ] SSRN URL (e.g. the one that triggered correlation id `bacbd8fa7639`: `https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6531478`) succeeds without `FIRECRAWL_LOW_VALUE`; the resulting summary clearly references content from the PDF body, not just the abstract.
- [ ] NBER URL (e.g. `https://www.nber.org/papers/w12345`) succeeds via URL rewrite, no HTML scrape required.
- [ ] Paywalled SSRN paper returns an abstract-only summary with an explicit "PDF unavailable (paywall)" note in the reply, not a generic extraction-failure error.
- [ ] Two URLs pointing at the same paper (arXiv `/abs/X` and `/pdf/X.pdf`) dedupe to one `request`.
- [ ] Both the HTML landing crawl and the PDF download are persisted as separate `crawl_results` rows for the same `request_id`, queryable by correlation id.
- [ ] Tests pass; CLI runner (`python -m app.cli.summary --url <arxiv-or-ssrn-url>`) succeeds end-to-end against a small fixture PDF.

## Definition of done

- All acceptance criteria green.
- Unit + integration tests added and passing in CI.
- `docs/SPEC.md` and `CLAUDE.md` updated.
- Deployed to the Pi via `make pi-deploy`; the SSRN URL from correlation id `bacbd8fa7639` re-tested manually and produces a meaningful summary.
- Issue file deleted from `docs/tasks/issues/` in the same commit as the implementation (per CLAUDE.md task lifecycle).
