# Test Plan: RAG-Optimized Fields
- Date: 2025-12-06
- Owner: AI Partner
- Related Docs: [REQ-rag-optimized-fields.md](../REQUIREMENTS/REQ-rag-optimized-fields.md), [TD-rag-optimized-fields.md](../TECH_DESIGNS/TD-rag-optimized-fields.md)

## Scope & Objectives
- Verify generation, validation, storage, embedding, and retrieval use of new RAG fields without regressing existing summary workflows.

## Test Approach
- Unit tests for contract validation, chunking, embedding builder.
- Integration tests for ingestion pipeline producing RAG fields.
- Retrieval tests for query expansion, hybrid search, and reranking.
-- Chroma metadata and scoping tests for validated upserts/queries and collection naming.

## Environments & Tooling
- Use existing test harness with pytest/pytest-asyncio.
- Chroma test instance or mocked store as used in current tests.

## Test Cases
- Contract validation: new fields required counts (20–30 keywords, 8–15 boosters), type checks, dedupe.
- Chunking: produces coherent 100–200 word slices; non-overlapping; fills local_summary/local_keywords.
- Embedding builder: includes text + local_summary + semantic_boosters; metadata persisted.
- Ingestion integration: article run yields RAG fields, stored in DB/metadata, embeddings created.
- Retrieval expansion: query_expansion_keywords applied; hybrid search uses local_keywords; boosters influence rerank ordering.
- Graceful degradation: missing boosters/keywords logs warning but does not crash.
- Chroma metadata validation: upsert rejects missing/invalid required fields (request_id, summary_id, user_scope, environment, text); cleans/limits tags and lists; rejects unknown keys.
- Chroma scoping/versioning: collection name follows `notes_{env}_{scope}_{version}`; env/user_scope enforced in upserted metadata and query filters; queries without user_scope/env default to configured values and do not bleed across scopes.

## Regression Coverage
- Existing summary contract tests still pass.
- URL processing and language/topic metadata unaffected.

## Non-Functional
- Basic performance smoke: chunk/embedding counts within expected bounds.
- Observability: correlation_id present in logs for failures.

## Entry / Exit Criteria
- Entry: RAG field implementation complete in code.
- Exit: All new tests pass; no regression failures; manual relevance spot-check shows improvement or parity.

## Risks & Mitigations
- Variance in LLM outputs: use fixed fixtures and mocks in tests.
- Token growth: cap booster usage in embedding builder and assert limits.

## Reporting
- CI results plus manual checklist for relevance evaluation.
