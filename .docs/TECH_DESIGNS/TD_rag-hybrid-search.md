# Tech Design: RAG Hybrid Search (BM25 + Embeddings + LLM Rerank)
- Date: 2025-12-07
- Owner: AI Partner
- Related Docs: [PRP-rag-hybrid-upgrade.md](../PROPOSALS/PRP-rag-hybrid-upgrade.md), [REQ_rag-hybrid-search.md](../REQUIREMENTS/REQ_rag-hybrid-search.md), [TEST_rag-hybrid-search.md](../TESTING/TEST_rag-hybrid-search.md)

## Summary
- Add hybrid retrieval that fuses BM25 (FTS5) and vector search, introduce windowed multi-vector retrieval using existing chunks, and apply OpenRouter-based reranking with fallbacks. Backfill existing articles into the upgraded index with observability and configuration controls.

## Context & Problem
- Current hybrid service combines FTS and vectors but lacks BM25 tuning, multi-vector/window context, and depends on a local cross-encoder reranker. Relevance and coherence are limited when returning isolated chunks or when keyword intent is strong.

## Goals / Non-Goals
- Goals: BM25+vector fusion with weights; windowed retrieval over chunk neighbors; LLM rerank via OpenRouter; full backfill; observability and flags.
- Non-Goals: Deploying local cross-encoders; multilingual-specific tuning; changing client-facing response schemas.

## Assumptions & Constraints
- Chroma remains the vector store; FTS via SQLite FTS5 already available.
- OpenRouter accessible; rerank calls must be budgeted and have fallbacks.
- Chunker already produces semantic slices; we can add window metadata without changing chunker output text.
- Collection versioning is available to isolate index upgrades.

## Requirements Traceability
- FR1 fusion → hybrid service weights, candidate merge.
- FR2 windowed retrieval → chunk/window metadata, grouping in vector results.
- FR3 rerank → OpenRouter rerank module, fallback logic.
- FR4 metadata → schema updates in vector/hybrid services.
- FR5 backfill → CLI/background job with batching/resume.
- FR6 config → env flags/weights, rerank top-K, window size, collection version.
- FR7 observability → structured logs, cid, timing, decision flags.

## Architecture
- Indexing pipeline: chunked content → embeddings per chunk (plus window context) → Chroma upsert with metadata (window_id, neighbors, section, topics, language, boosters, keywords, article-level expansion keywords) → optional BM25 doc body ingestion (FTS).
- Retrieval pipeline: query → query expansion (existing service) → parallel BM25 + vector search → fuse scores → optional OpenRouter rerank on top-K → return windowed chunks/snippets with metadata.
- Backfill job: read stored summaries/chunks → rebuild embeddings and BM25 docs → upsert into versioned collection with batching.

## Data Contracts
- Chroma metadata additions: `window_id` (str), `window_index` (int), `chunk_id` (str), `neighbor_chunk_ids` (list[str]), `section` (str|None), `topics` (list[str]), `language` (str|None), `query_expansion_keywords` (list[str]), `semantic_boosters` (list[str]), `local_keywords` (list[str]), `local_summary` (str).
- Required fields remain: `request_id`, `summary_id`, `user_scope`, `environment`, `text`, `tags`. Validation rejects unknown keys, trims list lengths, dedupes arrays, sanitizes strings.
- Collection naming: continue `notes_{environment}_{user_scope}_{version}`; new `CHROMA_COLLECTION_VERSION` value may be set for the upgraded index.
- Rerank request payload: `{query: str, candidates: [{text, title, score, url, metadata...}]}` sent via OpenRouter chat/completions; response expects ordered list of ids/scores. Graceful parse with fallback to fusion order.

## Flows
- Ingestion:
  1. Chunker yields chunks; assign `chunk_id` and ordered index.
  2. Build windows (default size 3: chunk plus neighbors). Compute `window_id` and `neighbor_chunk_ids`.
  3. Embedding text = chunk text + local_summary + top semantic_boosters (cap) + optional neighbor bleed (small context) to stay in budget.
  4. Upsert embedding with metadata to Chroma; attach article-level `query_expansion_keywords` and `semantic_boosters`.
  5. Build BM25 doc body using chunk text + local keywords + titles/snippets; upsert to FTS (existing LocalTopicSearchService inputs).
- Retrieval:
  1. Expand query (existing query_expansion_service).
  2. Run BM25/FTS (expanded) and vector search (original). Vector search should surface window-aware results (group by window_id).
  3. Fuse scores using weights; dedupe by window_id/url; keep top N.
  4. If rerank enabled, send top-K fused candidates to OpenRouter; apply returned ordering; fallback to fusion ordering on error/timeout.
  5. Return window-level results containing primary chunk text/snippet and neighbor references for display.
- Backfill:
  - CLI command iterates stored summaries/chunks, rebuilds embeddings+metadata, writes to new collection version; supports `--resume` via last processed id; logs progress with cid.

## Algorithms / Logic
- Fusion: normalized BM25 (rank-based) + vector similarity weighted sum; weights configurable (env).
- Windowing: create window_id per chunk index; neighbor_chunk_ids +/- window_radius within same article; metadata carries both chunk and window positions.
- Rerank: send top-K (config) fused results; include text = snippet/local_summary + optional chunk text (truncated); use timeout; on failure, return fusion order.
- Candidate dedupe: prefer highest combined score per window_id/url.

## Error Handling & Retries
- Rerank: timeout with fallback; log cid, reason; do not fail request.
- Chroma upsert/query: catch and log validation errors with cid; skip bad records, continue batch.
- Backfill: batch failures logged; resume supported via checkpoint.

## Security & Privacy
- No secrets in metadata; redact Authorization in logs.
- Enforce `user_scope` and `environment` filters on upsert/query; do not mix scopes.

## Performance & Scalability
- Limit embedding text length and booster count; cap candidates for rerank.
- Batch upserts and backfill jobs; use collection versioning to avoid locks.
- Keep window size small (default 3) to bound duplication.

## Operations
- Config flags/env: `HYBRID_FTS_WEIGHT`, `HYBRID_VECTOR_WEIGHT`, `HYBRID_MAX_RESULTS`, `HYBRID_WINDOW_SIZE`, `HYBRID_FUSION_TOPK`, `RERANK_ENABLED`, `RERANK_TOPK`, `RERANK_TIMEOUT_SEC`, `CHROMA_COLLECTION_VERSION`.
- Logging: fusion scores, window ids, rerank used, fallback reason, timings, cid.
- Metrics (if available): rerank hit rate, latency, backfill progress.

## Testing Strategy
- Unit: fusion weighting, window grouping, metadata validation, rerank fallback behavior.
- Integration: retrieval pipeline uses fusion+rERANK over mocked stores; window results coherent.
- Backfill: dry-run/resume; validates collection naming and metadata schema.
- Regression: existing summary/RAG field tests remain passing.

## Risks / Trade-offs
- Latency/cost from rerank; mitigated via caps and fallback.
- Index bloat from windows; mitigated by small window radius and collection versioning.
- Quality variance from LLM rerank; mitigated by heuristics fallback and logging for tuning.

## Alternatives Considered
- Keep local cross-encoder rerank (rejected: resource footprint).
- No rerank (rejected: weaker precision).
- Smaller window radius of 0 (rejected: loses context coherence).

## Open Questions
- Exact defaults for `RERANK_TIMEOUT_SEC`, `RERANK_TOPK`, and whether to vary per channel (Telegram/API).
- Whether to force new collection version vs migrate in place.
