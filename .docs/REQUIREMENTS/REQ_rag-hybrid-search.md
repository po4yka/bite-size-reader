# RAG Hybrid Search (BM25 + Embeddings + LLM Rerank)
- Date: 2025-12-07
- Owner: AI Partner
- Related Docs: [PRP-rag-hybrid-upgrade.md](../PROPOSALS/PRP-rag-hybrid-upgrade.md), [TD_rag-hybrid-search.md](../TECH_DESIGNS/TD_rag-hybrid-search.md), [TEST_rag-hybrid-search.md](../TESTING/TEST_rag-hybrid-search.md)

## Background
- Current retrieval underuses keyword signals and lacks reranking; coherence suffers because chunks are returned individually.
- We already chunk content and store embeddings; hybrid scaffolding exists but is not fused or reranked.

## Scope
- In scope: BM25 + embedding fusion; multi-vector windowed retrieval; OpenRouter-based reranking with fallback; metadata/schema updates; backfill of existing articles; observability and controls.
- Out of scope: Local cross-encoder deployment; multilingual specialization beyond current language detection; non-article sources beyond reuse of existing pipeline.

## Functional Requirements
- FR1: Provide hybrid retrieval that fuses BM25 (keyword) and vector search; configurable weights and cutoffs.
- FR2: Support windowed retrieval: return chunk windows (e.g., chunk ± neighbors) as coherent units; store necessary metadata.
- FR3: Apply LLM-based reranking (OpenRouter) to top-K fused candidates; fallback to fusion-only on timeout/error/flag off.
- FR4: Ensure metadata includes window identifiers, neighbor relations, topics/language, and remains access-scoped.
- FR5: Backfill existing articles into the upgraded hybrid index without breaking existing data; idempotent and resumable.
- FR6: Provide configuration flags for fusion weights, rerank enablement, rerank candidate size, window size, collection/versioning.
- FR7: Preserve and expose observability: correlation_id, timing, fusion/rerank decisions; redact sensitive data.

## Non-Functional Requirements
- Latency: Rerank call budgeted; must fall back within timeout to avoid user-visible stalls.
- Reliability: Retrieval must degrade gracefully if BM25 or rerank unavailable.
- Compatibility: Existing summaries remain valid; no breaking schema changes to clients.
- Performance: Index growth bounded; batch operations to avoid long locks.
- Security: Enforce user_scope/environment scoping; no secrets in metadata.

## Data & Schema
- Add metadata fields: `window_id`, `window_index`, `chunk_id`, `neighbor_chunk_ids`, `section`, `topics`, `language`, `query_expansion_keywords`, `semantic_boosters`, `local_keywords`, `local_summary`.
- Chroma metadata validation must accept and sanitize the above, keeping required fields unchanged (request_id, summary_id, user_scope, environment, text, tags).
- Collection/version naming must continue to enforce scoping and versioning; new version if needed.

## Dependencies
- LLM via OpenRouter for rerank.
- Existing chunker, embedding service, hybrid/vector search services, Chroma index.
- Config/env management for new flags and weights.

## Risks / Constraints
- Latency/cost from rerank; mitigated via caps and fallback.
- Backfill duration and potential storage growth.
- Quality variance in LLM rerank; rely on heuristics as guardrails.

## Acceptance Criteria
- Hybrid fusion and windowed retrieval are used in production paths (Telegram/API) with configurable weights.
- Rerank improves ordering; fallback works without errors when disabled/failing.
- Metadata stored/validated with window and chunk context; access scoping intact.
- Backfill completes or can be resumed; no data loss; collection/versioning correct.
- Observability logs show fusion scores, rerank usage, correlation_ids.

## Open Questions
- Exact rerank timeout and candidate K defaults for Telegram vs API.
- Whether to create a new Chroma collection version or reuse existing with migration.
