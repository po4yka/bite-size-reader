# RAG Hybrid Upgrade (BM25 + Embeddings + LLM Rerank)
- Date: 2025-12-07
- Owner: AI Partner
- Related Docs: [TD-rag-hybrid-search.md](../TECH_DESIGNS/TD_rag-hybrid-search.md), [REQ-rag-hybrid-search.md](../REQUIREMENTS/REQ_rag-hybrid-search.md), [TEST-rag-hybrid-search.md](../TESTING/TEST_rag-hybrid-search.md)

## Context
- Current retrieval relies mainly on embeddings with limited keyword signals; relevance plateaus on sparse or specific queries.
- We have chunked content and hybrid scaffolding but lack BM25 fusion, multi-vector windowing, and reranking.
- Stakeholders: Telegram bot users (owner), mobile API consumers, maintainers needing predictable relevance and latency.

## Goals
- Add hybrid retrieval combining BM25 and embeddings with tunable fusion.
- Introduce windowed, multi-vector retrieval over existing chunker output for better coherence.
- Apply LLM-based reranking (OpenRouter) on fused candidates with graceful fallback.
- Backfill existing articles into the upgraded index without data loss.
- Maintain observability and access-control guarantees.

## Non-Goals
- Deploying local cross-encoder rerankers (GPU/CPU heavy) in this phase.
- Multilingual retrieval tuning beyond current language detection.
- Schema changes beyond retrieval metadata and indexing needs.

## Options Considered
- Option A: Embedding-only with heuristic fusion (status quo). Pros: simple; Cons: misses keyword intent, weaker recall.
- Option B: Hybrid BM25 + embedding fusion without rerank. Pros: cheaper; Cons: ordering still weak on nuanced queries.
- Option C: Hybrid fusion + LLM rerank (OpenRouter). Pros: best relevance; Cons: extra latency/cost, needs fallbacks.

## Decision
- Choose Option C: BM25 + embedding fusion with OpenRouter rerank. Use feature flags/weights to tune, and fallback to fusion-only when rerank unavailable or over budget.

## Risks / Trade-offs
- Latency and cost from rerank calls; mitigation: cap candidates, make rerank optional, add timeouts/fallback.
- Index bloat from windowed multi-vectors; mitigation: size caps, pruning, batch backfill.
- Backfill duration; mitigation: batch jobs with resume, collection versioning.
- Quality variance from LLM rerank; mitigation: heuristics fallback, logging for evaluation.

## Milestones / Timeline
- M1: Proposal/requirements/design approved (2025-12-07).
- M2: Implementation of fusion, windowing, rerank integration (2025-12-09).
- M3: Backfill tooling ready and dry-run (2025-12-10).
- M4: Tests/rollout checks pass; enable in staging/owner bot (2025-12-11).

## Open Questions
- Rerank budget/latency thresholds per query path (Telegram vs API) and cutoff for skipping rerank.
- Backfill scope sequencing (all articles vs staged by recency) once tooling lands.
