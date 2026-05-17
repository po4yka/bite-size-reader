---
title: Add a third embedding provider (Voyage AI, Cohere, or OpenAI text-embedding-3)
status: backlog
area: llm
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add a third embedding provider (Voyage AI, Cohere, or OpenAI text-embedding-3) #repo/ratatoskr #area/llm #status/backlog 🔼

## Objective

`app/infrastructure/embedding/embedding_factory.py:22-35` is a
clean 2-branch switch (`local` | `gemini`) with an explicit
`Unknown embedding provider` error — textbook port awaiting a
third adapter. Voyage `voyage-3-large` and Cohere
`embed-english-v3.0` outperform Gemini on retrieval benchmarks;
OpenAI `text-embedding-3-large` is the de facto baseline.

## Context

- Factory:
  `app/infrastructure/embedding/embedding_factory.py:22-35`.
- Protocol:
  `app/infrastructure/embedding/embedding_protocol.py`.
- Existing providers: local sentence-transformers and Gemini.

## Scope

- Add at least one new provider (recommend Voyage AI first;
  pricing + multilingual + retrieval quality) honouring
  `EmbeddingServiceProtocol`.
- Wire `EMBEDDING_PROVIDER=voyage` (or `cohere` / `openai`)
  through `EmbeddingConfig`.
- Validate Qdrant collection dimension at startup — refuse to
  start if the provider's output dimension doesn't match the
  existing collection (force operator to re-index or pick a
  different provider).
- Document the new provider in
  `docs/guides/setup-qdrant-vector-search.md` and
  `docs/reference/environment-variables.md`.

## Acceptance criteria

- [ ] Switching `EMBEDDING_PROVIDER` to the new value works
  end-to-end (summary embedding → Qdrant write → search hit).
- [ ] Dimension-mismatch refusal logged with a clear remediation
  hint.
- [ ] Unit + integration test cover the new adapter.
- [ ] Docs updated.

## References

- Factory:
  `app/infrastructure/embedding/embedding_factory.py:22-35`
- Protocol:
  `app/infrastructure/embedding/embedding_protocol.py`
