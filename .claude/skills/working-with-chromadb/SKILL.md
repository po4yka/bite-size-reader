---
name: working-with-chromadb
description: >
  Manage ChromaDB vector store -- health checks, backfilling, search testing,
  embedding coverage, collection management, and debugging. Trigger keywords:
  ChromaDB, Chroma, vector store, embeddings, semantic search, backfill,
  embedding coverage, vector search, collection, similarity search.
version: 2.1.0
allowed-tools: Bash, Read, Grep
---

# ChromaDB Vector Store Management

Manage ChromaDB health, embeddings, search quality, and debugging for the Ratatoskr vector search subsystem.

## Dynamic Context

```bash
!python .claude/skills/working-with-chromadb/scripts/chroma-health-check.py 2>/dev/null || echo "ChromaDB: unreachable"
```

```bash
!sqlite3 data/ratatoskr.db "SELECT (SELECT COUNT(*) FROM summaries) as total_summaries, (SELECT COUNT(*) FROM summary_embeddings) as total_embeddings"
```

```bash
!sqlite3 data/ratatoskr.db "SELECT COUNT(*) as recent_embeddings FROM summary_embeddings WHERE created_at > datetime('now', '-24 hours')"
```

## Configuration

| Env Var | Default | Description |
|---|---|---|
| `CHROMA_HOST` | `http://localhost:8000` | Chroma HTTP endpoint (scheme + host) |
| `CHROMA_AUTH_TOKEN` | `None` | Optional bearer token for secured deployments |
| `CHROMA_ENV` | `dev` | Environment label for collection namespacing |
| `CHROMA_USER_SCOPE` | `public` | User/tenant scope for collection namespacing |
| `CHROMA_COLLECTION_VERSION` | `v1` | Collection version suffix |
| `CHROMA_REQUIRED` | `false` | Fail on startup if Chroma unavailable |
| `CHROMA_CONNECTION_TIMEOUT` | `10.0` | HTTP client timeout in seconds |
| `EMBEDDING_PROVIDER` | `local` | Embedding provider: `local` or `gemini` |
| `GEMINI_API_KEY` | -- | Required when `EMBEDDING_PROVIDER=gemini` |
| `GEMINI_EMBEDDING_MODEL` | `gemini-embedding-2-preview` | Gemini model name |
| `GEMINI_EMBEDDING_DIMENSIONS` | `768` | Gemini embedding dimensions (1-3072) |
| `EMBEDDING_MAX_TOKEN_LENGTH` | `512` | Max token length for embedding text |

## Core Workflows

### Health Check

```bash
python .claude/skills/working-with-chromadb/scripts/chroma-health-check.py
```

Output: `ChromaDB: healthy | collection=notes_dev_public_v1 | docs=1234 | env=dev | scope=public`

### Backfilling Embeddings into Chroma

**Full backfill** (skips existing embeddings):

```bash
python -m app.cli.backfill_chroma_store --db=data/ratatoskr.db
```

**Incremental** (limit to recent):

```bash
python -m app.cli.backfill_chroma_store --db=data/ratatoskr.db --limit=50
```

**Force regeneration** (re-embeds everything):

```bash
python -m app.cli.backfill_chroma_store --db=data/ratatoskr.db --force
```

**Custom Chroma target:**

```bash
python -m app.cli.backfill_chroma_store --db=data/ratatoskr.db --chroma-host=http://chroma:8000 --chroma-env=prod --chroma-scope=user123
```

### Search Testing

**Vector search:**

```bash
python .claude/skills/working-with-chromadb/scripts/chroma-search-test.py "machine learning" --limit 5
```

**Language-specific:**

```bash
python .claude/skills/working-with-chromadb/scripts/chroma-search-test.py "neural networks" --lang en --limit 10
```

**Existing CLI tools:**

```bash
# Topic search (FTS5 + vector hybrid)
python -m app.cli.search "query text"

# Compare search backends side-by-side
python -m app.cli.search_compare "query text"
```

### Embedding Coverage Check

```bash
sqlite3 data/ratatoskr.db << 'EOF'
.mode column
.headers on
SELECT
    (SELECT COUNT(*) FROM summaries) as total_summaries,
    (SELECT COUNT(*) FROM summary_embeddings) as total_embeddings,
    (SELECT COUNT(*) FROM summaries s
     LEFT JOIN summary_embeddings se ON s.id = se.summary_id
     WHERE se.id IS NULL) as missing_embeddings;
EOF
```

## Common DB Queries

### Coverage by Language

```bash
sqlite3 data/ratatoskr.db << 'EOF'
.mode column
.headers on
SELECT s.lang, COUNT(*) as summaries,
       SUM(CASE WHEN se.id IS NOT NULL THEN 1 ELSE 0 END) as with_embeddings
FROM summaries s
LEFT JOIN summary_embeddings se ON s.id = se.summary_id
GROUP BY s.lang;
EOF
```

### Missing Embeddings

```bash
sqlite3 data/ratatoskr.db << 'EOF'
.mode column
.headers on
SELECT s.id, s.lang, r.input_url
FROM summaries s
JOIN requests r ON s.request_id = r.id
LEFT JOIN summary_embeddings se ON s.id = se.summary_id
WHERE se.id IS NULL
LIMIT 20;
EOF
```

### Model Distribution

```bash
sqlite3 data/ratatoskr.db "SELECT model_name, COUNT(*) as count FROM summary_embeddings GROUP BY model_name;"
```

### Recent Embedding Activity

```bash
sqlite3 data/ratatoskr.db << 'EOF'
.mode column
.headers on
SELECT DATE(created_at) as date, COUNT(*) as count
FROM summary_embeddings
GROUP BY DATE(created_at)
ORDER BY date DESC
LIMIT 7;
EOF
```

## Architecture Overview

### Embedding Pipeline

```
Summary created -> SummaryEmbeddingGenerator
                       |
                       v
                  EmbeddingService (language -> model selection)
                       |
                       v
                  serialize_embedding() -> summary_embeddings table (SQLite)
                       |
                       v
                  MetadataBuilder.prepare_chunk_windows_for_upsert()
                       |
                       v
                  ChromaVectorStore.upsert_notes() -> Chroma collection
```

### Search Flow

```
Query text -> detect_language() -> EmbeddingService.generate_embedding(task_type="query")
                                       |
                                       v
                                  ChromaVectorSearchService.search()
                                       |
                                       v
                                  ChromaVectorStore.query() -> Chroma
                                       |
                                       v
                                  ChromaVectorSearchResult[] (similarity = 1 - cosine_distance)
```

### Key Service Boundaries

- **EmbeddingService** (`app/infrastructure/embedding/embedding_service.py`) -- model loading, language-based model selection, vector generation
- **EmbeddingFactory** (`app/infrastructure/embedding/embedding_factory.py`) -- creates local or Gemini embedding service based on config
- **SummaryEmbeddingGenerator** (`app/application/services/summary_embedding_generator.py`) -- orchestrates embedding generation for summaries
- **MetadataBuilder** (`app/infrastructure/vector/metadata_builder.py`) -- builds Chroma metadata dicts and chunk windows
- **ChromaVectorStore** (`app/infrastructure/vector/chroma_store.py`) -- Chroma client wrapper with graceful degradation
- **ChromaVectorSearchService** (`app/infrastructure/search/chroma_vector_search_service.py`) -- high-level search API

## Key Project Files

| File | Purpose |
|---|---|
| `app/infrastructure/vector/chroma_store.py` | ChromaVectorStore -- client wrapper, upsert/query/delete |
| `app/infrastructure/vector/chroma_schemas.py` | ChromaMetadata, ChromaQueryFilters (Pydantic models) |
| `app/infrastructure/search/chroma_vector_search_service.py` | ChromaVectorSearchService -- semantic search API |
| `app/infrastructure/embedding/embedding_service.py` | EmbeddingService -- local sentence-transformers |
| `app/infrastructure/embedding/gemini_embedding_service.py` | GeminiEmbeddingService -- cloud Gemini provider |
| `app/infrastructure/embedding/embedding_factory.py` | create_embedding_service() -- provider factory |
| `app/infrastructure/embedding/embedding_protocol.py` | EmbeddingServiceProtocol -- interface |
| `app/application/services/summary_embedding_generator.py` | SummaryEmbeddingGenerator -- embedding orchestrator |
| `app/infrastructure/vector/metadata_builder.py` | MetadataBuilder -- Chroma metadata construction |
| `app/config/integrations.py` | ChromaConfig, EmbeddingConfig (Pydantic settings) |
| `app/cli/backfill_chroma_store.py` | CLI tool: sync embeddings into Chroma |
| `app/cli/search_compare.py` | CLI tool: compare FTS5 vs vector search |

## Important Notes

1. **Graceful degradation:** When `CHROMA_REQUIRED=false` (default), all Chroma operations silently return empty results if Chroma is unreachable. Check `vector_store.available` property.

2. **Dual storage:** Embeddings are stored in both SQLite (`summary_embeddings` table as packed float32 blobs) and Chroma (as vectors with rich metadata). SQLite is the source of truth; Chroma is the search index.

3. **Language-model selection:** Language detection determines which embedding model is used. Mismatched models between indexing and querying produce poor similarity scores. See `DEFAULT_MODELS` in `embedding_service.py`.

4. **Metadata validation:** `ChromaMetadata` uses `extra="forbid"` -- unknown fields cause validation errors. The store injects `environment` and `user_scope` automatically, stripping them from user-provided metadata.

5. **Chunk windows:** One summary can produce multiple Chroma documents via `MetadataBuilder.prepare_chunk_windows_for_upsert()`. This means Chroma doc count >= SQLite embedding count.

6. **Similarity formula:** `similarity = 1.0 - cosine_distance`, clamped to [0.0, 1.0]. Higher is better.

## Reference Files

- [Chroma Schema Reference](references/chroma-schema-reference.md) -- full metadata fields, query filter logic, ID generation, collection settings
- [Debugging Scenarios](references/debugging-scenarios.md) -- 6 common failure scenarios with diagnosis and fixes
