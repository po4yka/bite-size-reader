# Test Plan: RAG Hybrid Search (BM25 + Embeddings + LLM Rerank)
- Date: 2025-12-07
- Owner: AI Partner
- Related Docs: [REQ_rag-hybrid-search.md](../REQUIREMENTS/REQ_rag-hybrid-search.md), [TD_rag-hybrid-search.md](../TECH_DESIGNS/TD_rag-hybrid-search.md)

## Scope & Objectives
- Verify hybrid BM25+embedding fusion, windowed chunk retrieval, OpenRouter reranking, and backfill tooling without regressing existing summary/RAG behaviors.

## Test Approach
- Unit: metadata builders (chunk windows), hybrid fusion logic, rerank fallback, Chroma metadata validation.
- Integration: embedding/upsert path via event handler, hybrid search against mocked services, backfill CLI dry-run.
- Optional E2E (manual): search commands in Telegram/API with rerank toggle.

## Environments & Tooling
- pytest/pytest-asyncio; existing chroma test doubles.
- Config flags: rerank enabled/disabled, fusion weights, window size, CHROMA_COLLECTION_VERSION.

## Test Cases
- TC1 Chunk window builder: semantic_chunks → window_id/window_index/neighbor ids; text includes local_summary + boosters; tags/topics propagated.
- TC2 Event handler ingest: semantic_chunks produce multiple embeddings upserted; fallback to summary-only when chunks missing.
- TC3 Hybrid fusion: BM25 + vector scores combine and dedupe by window_id/url; respects max_results.
- TC4 Rerank happy path: OpenRouter rerank orders top-K; scores attached; fallback preserves fusion order on timeout/error.
- TC5 Chroma metadata validation: allows window/local fields; rejects empty text; dedup lists; enforces scope/environment.
- TC6 Backfill CLI: processes summaries with chunks; batches upserts; resumes with `--limit`; skips empty payloads.
- TC7 Search CLI compare: runs without errors using new Chroma path; prints counts and overlap.
- TC8 Regression: existing summary contract and RAG field tests still pass.

## Regression Coverage
- Summary contract, query expansion, note text builder, hybrid search existing cases.

## Non-Functional
- Latency budget: rerank timeout fallback verified; vector count bounded by window size and top_k.
- Observability: logs include cid/decision flags in search/ingest paths (spot-check).

## Entry / Exit Criteria
- Entry: Code + configs updated; Chroma reachable in test env.
- Exit: New tests pass; regressions green; manual spot-check (optional) shows coherent window results.

## Risks & Mitigations
- Rerank variability: mock OpenRouter in tests; cap timeouts.
- Index bloat: verify window size cap; inspect batch sizes in logs.

## Reporting
- CI pytest results; manual notes for rerank spot-checks.
