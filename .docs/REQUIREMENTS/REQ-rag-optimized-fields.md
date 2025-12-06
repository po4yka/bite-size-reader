# RAG-Optimized Fields for Article Pipeline
- Date: 2025-12-06
- Owner: AI Partner
- Related Docs: [TD-rag-optimized-fields.md](../TECH_DESIGNS/TD-rag-optimized-fields.md), [TEST-rag-optimized-fields.md](../TESTING/TEST-rag-optimized-fields.md)

## Background
- Current article pipeline produces TLDR and 250/500-word summaries but lacks RAG-focused metadata needed for stronger recall/precision in hybrid retrieval.
- Chroma-based hybrid search exists; we need richer query expansion, chunk metadata, and embedding composition to improve relevance.

## Scope
- In scope:
  - Generate RAG metadata for articles: query_expansion_keywords, semantic_boosters, semantic chunks with local summaries/keywords.
  - Integrate metadata into persistence, embeddings, and retrieval flows.
  - Update prompts/agents to emit the new fields.
  - Update search pipeline to leverage the fields (expansion, reranking, keyword fusion).
- Out of scope:
  - Multilingual variants, stance/sentiment fields (future work).
  - Non-article sources (e.g., YouTube) unless reused via existing article path.

## Functional Requirements
- FR1: For each article, generate 20–30 English `query_expansion_keywords` (synonyms, alt phrasings, specific/general search intents).
- FR2: Generate 8–15 English `semantic_boosters` (standalone, embedding-friendly sentences capturing core relationships/trade-offs/concepts).
- FR3: Chunk article into 100–200 word semantic units (non-overlapping, coherent). For each chunk produce `local_summary` (1–2 standalone sentences) and `local_keywords` (3–8 phrases).
- FR4: Attach metadata per article/chunk: article_id, topics, language, section (if applicable), new RAG fields.
- FR5: Embedding input per chunk must include `text + local_summary + semantic_boosters`; retain raw text for display; store all fields in metadata for hybrid retrieval.
- FR6: Retrieval must expand user queries using `query_expansion_keywords`, re-rank using `semantic_boosters`, and combine vector search with keyword search leveraging `local_keywords`.
- FR7: Data stored in structured JSON; contract validated before persistence.

## Non-Functional Requirements
- Consistency: Deterministic schema, validation errors surfaced with correlation IDs.
- Performance: Generation should not regress SLA materially; chunking/embedding steps should batch where possible.
- Reliability: Graceful degradation if fields missing; do not break existing summary flow.
- Observability: Log generation and retrieval decisions with correlation IDs; redact sensitive data.

## Data & Schema
- Extend summary contract to include `query_expansion_keywords`, `semantic_boosters`, chunk-level `local_summary`, `local_keywords`, and chunk metadata.
- Persist new fields alongside summaries and embeddings; ensure Chroma/hybrid index stores metadata for keyword filtering/reranking.
- SPEC.md must document new JSON shape.

## Dependencies
- LLM prompts/workflows (OpenRouter) for generation.
- Content chunker and embedding services.
- Chroma hybrid search components (vector_search_service, hybrid_search_service, query_expansion_service, reranking_service).

## Risks / Constraints
- Token/latency increase from richer prompts and embeddings.
- Quality variance from LLM outputs; need validation guards.
- Backward compatibility with existing data; migrations may be required.
- Possible storage bloat from extra metadata fields.

## Acceptance Criteria
- New fields generated automatically for ingested articles.
- Chunks are coherent, non-overlapping, 100–200 words.
- Embeddings include text + local_summary + semantic_boosters; metadata stored for hybrid search.
- Retrieval uses query expansion, reranking via boosters, and keyword fusion; relevance improves in evaluation.
- JSON validated against updated contract; SPEC.md reflects fields.

## Open Questions
- Do we need language-conditional generation for non-English articles now, or only future multilingual extension?
- Should we backfill existing articles or only apply to new ingests in this phase?
