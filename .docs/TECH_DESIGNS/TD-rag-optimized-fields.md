# Tech Design: RAG-Optimized Fields
- Date: 2025-12-06
- Owner: AI Partner
- Related Docs: [REQ-rag-optimized-fields.md](../REQUIREMENTS/REQ-rag-optimized-fields.md), [TEST-rag-optimized-fields.md](../TESTING/TEST-rag-optimized-fields.md)

## Summary
- Extend article ingestion to generate RAG-focused metadata (query_expansion_keywords, semantic_boosters, semantic chunks with local summaries/keywords), persist it, embed with enriched context, and leverage it in Chroma hybrid retrieval (vector + keyword + rerank).

## Context & Problem
- Existing pipeline outputs TLDR/short summaries only; retrieval quality plateaus without query expansion, chunk metadata, and booster signals.
- Chroma hybrid search is available but underutilized; we need structured fields to power expansion and reranking.

## Goals / Non-Goals
- Goals: Generate new RAG fields, store them, embed enriched text, and update retrieval logic to consume them.
- Non-Goals: Multilingual variants, sentiment/stance; non-article sources.

## Assumptions & Constraints
- LLM (OpenRouter) can produce required fields within token limits.
- Chroma remains the vector store; hybrid keyword search available.
- Chunk size target 100–200 words; non-overlapping slices.

## Requirements Traceability
- FR1–FR7 mapped to: prompt/workflow updates (FR1-3), contract/schema (FR4-5), embedding and retrieval services (FR6), validation (FR7).

## Architecture
- Generation path: URL → content_extractor → chunker (semantic chunks) → LLM summarization with RAG fields → validation (summary_contract) → persistence (DB + embeddings) → Chroma ingest.
- Retrieval path: query → query_expansion_service (use stored expansion keywords) → hybrid search (vector on enriched embeddings + keyword using local_keywords) → reranking_service incorporating semantic_boosters → response formatting.

## Data Contracts
- Summary JSON adds:
  - `query_expansion_keywords: List[str]` (20–30)
  - `semantic_boosters: List[str]` (8–15)
  - `chunks: List[{"text": str, "local_summary": str, "local_keywords": List[str], "section": Optional[str], "language": str, "topics": List[str], "article_id": str}]`
- Embedding payload per chunk: `text + local_summary + semantic_boosters` (dedup, newline-joined).
- Metadata persisted with chunk and embedding: article_id, topics, language, section, local_keywords, local_summary, semantic_boosters reference, query_expansion_keywords (article-level).

## Flows
- Ingestion:
  1. Normalize URL, fetch article content.
  2. Chunker splits content into 100–200 word slices; assigns section/topic/language if available.
  3. LLM prompt returns summaries plus new fields; validate via summary_contract.
  4. Persist article summary + RAG fields; store chunks with metadata.
  5. Build embeddings per chunk using enriched text; upsert to Chroma with metadata.
- Retrieval:
  1. Receive query; expand using stored query_expansion_keywords (article-level) plus model-based expansion fallback if needed.
  2. Run hybrid search: vector over enriched embeddings; keyword search over local_keywords + topics.
  3. Re-rank candidates using semantic_boosters similarity and chunk-local signals.
  4. Return chunk text for display; include metadata for traceability.

## Algorithms / Logic
- Chunking: word-based segmentation with semantic boundaries; enforce non-overlap; pad/merge if under 80 words; cap at 200 words.
- Booster selection: LLM instructed to produce standalone sentences; validation ensures count and non-empty strings.
- Expansion keywords: LLM generates varied phrasings (synonyms, general/specific intents); enforce 20–30 unique phrases.
- Embedding text builder: concatenate chunk text + local_summary + top-N semantic_boosters (cap e.g., 10) with separators; remove duplicates; trim to token budget.

## Error Handling & Retries
- Validation failures surface with correlation IDs; retry LLM generation up to existing workflow limits.
- If new fields missing, fall back to existing summary-only behavior but log warning.
- Chroma upsert errors: retry with backoff; skip problematic chunks but keep request recorded.

## Security & Privacy
- No secrets in metadata; redact Authorization in logs.
- Preserve access control unchanged.

## Performance & Scalability
- Batch embeddings per article; reuse boosters across chunks to reduce tokens.
- Keep chunk count manageable via target size.

## Operations
- Observability: log generation counts, chunk sizes, expansion list sizes; include correlation_id.
- Feature flag (if available) can gate new RAG fields rollout.

## Testing Strategy
- Contract validation tests for new fields.
- Chunker tests for size/coherence and metadata.
- Embedding builder tests for composition.
- Retrieval tests for expansion + rerank integration.

## Risks / Trade-offs
- Larger prompts/embeddings increase cost and latency.
- Booster/keyword quality tied to LLM output; may need heuristic filtering.

## Alternatives Considered
- Generate expansions via separate model call (rejected: latency).
- Use smaller chunk size (<100 words) (rejected: more chunks, cost).

## Open Questions
- Do we backfill existing articles or only new ingests in initial rollout?
- How to cap booster count used in embedding to balance cost vs quality?
