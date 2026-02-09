# CLI Commands Reference

Complete reference for all command-line tools in Bite-Size Reader.

**Audience:** Developers, Operators
**Type:** Reference
**Related:** [How-To Guides](../how-to/), [TROUBLESHOOTING](../TROUBLESHOOTING.md)

---

## Overview

Bite-Size Reader provides CLI tools for:

- Testing summarization without Telegram (`summary.py`)
- Database migrations (`migrate_db.py`)
- Search functionality testing (`search.py`, `search_compare.py`)
- Embedding and vector store management (`backfill_embeddings.py`, `backfill_chroma_store.py`)
- Performance optimization (`add_performance_indexes.py`)
- MCP server (`mcp_server.py`)

**Common Pattern:** `python -m app.cli.<command> [options]`

---

## Summary Runner

**Command:** `python -m app.cli.summary`

**Purpose:** Test URL summarization without Telegram bot.

### Basic Usage

```bash
# Summarize single URL
python -m app.cli.summary --url https://example.com/article

# Multiple URLs (interactive mode)
python -m app.cli.summary --accept-multiple
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--url` | string | - | URL to summarize (required if not using `--accept-multiple`) |
| `--accept-multiple` | flag | false | Interactive mode: accept multiple URLs |
| `--json-path` | string | - | Save summary JSON to file |
| `--log-level` | string | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `--lang` | string | auto | Force language (en, ru, or auto-detect) |
| `--skip-web-search` | flag | false | Disable web search enrichment |
| `--output-format` | string | pretty | Output format (pretty, json, minimal) |

### Examples

**Basic Summarization:**

```bash
python -m app.cli.summary --url https://techcrunch.com/2026/01/15/ai-breakthrough/
```

**Debug Mode with JSON Output:**

```bash
python -m app.cli.summary \
  --url https://example.com/article \
  --log-level DEBUG \
  --json-path output.json
```

**Multiple URLs (Interactive):**

```bash
python -m app.cli.summary --accept-multiple
# Enter URLs one per line, Ctrl+D to finish
https://example.com/article1
https://example.com/article2
```

**Force Language:**

```bash
python -m app.cli.summary \
  --url https://habr.com/ru/post/123456/ \
  --lang ru
```

### Output

**Pretty Format (default):**

```
=== Summary for: https://example.com/article ===

Summary (250 chars):
  [summary text...]

Summary (1000 chars):
  [detailed summary...]

TL;DR:
  [one-sentence takeaway...]

Key Ideas:
  - [idea 1]
  - [idea 2]
  ...

[full summary JSON follows...]
```

**JSON Format:**

```bash
python -m app.cli.summary --url https://example.com --output-format json | jq .
```

**Minimal Format:**

```bash
python -m app.cli.summary --url https://example.com --output-format minimal
# Only prints TL;DR and key ideas
```

### Exit Codes

- `0` - Success
- `1` - Validation error (invalid URL, missing env vars)
- `2` - Content extraction failed
- `3` - LLM summarization failed
- `4` - Summary validation failed

---

## Database Migration

**Command:** `python -m app.cli.migrate_db`

**Purpose:** Apply database migrations.

### Basic Usage

```bash
# Apply all pending migrations
python -m app.cli.migrate_db

# Check migration status (dry-run)
python -m app.cli.migrate_db --check
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--check` | flag | false | Check migration status without applying |
| `--target-version` | int | latest | Migrate to specific version |
| `--rollback` | flag | false | Rollback last migration (use with caution) |

### Examples

**Check Status:**

```bash
python -m app.cli.migrate_db --check

# Output:
# Current version: 5
# Pending migrations:
#   006_add_quality_scores.sql
#   007_add_vector_search.sql
```

**Apply All Pending:**

```bash
python -m app.cli.migrate_db

# Output:
# Applying migration 006_add_quality_scores.sql... OK
# Applying migration 007_add_vector_search.sql... OK
# Database migrated to version 7
```

**Migrate to Specific Version:**

```bash
python -m app.cli.migrate_db --target-version 6
```

**Rollback (Dangerous):**

```bash
# Backup first!
cp data/app.db data/app.db.backup

python -m app.cli.migrate_db --rollback
```

### Migration Files

**Location:** `app/cli/migrations/`

**Format:** `001_description.sql`, `002_description.sql`, etc.

**Example Migration:**

```sql
-- 006_add_quality_scores.sql
ALTER TABLE summaries ADD COLUMN quality_score_accuracy REAL;
ALTER TABLE summaries ADD COLUMN quality_score_coherence REAL;
ALTER TABLE summaries ADD COLUMN quality_score_completeness REAL;

CREATE INDEX idx_summaries_quality ON summaries(quality_score_accuracy);
```

---

## Search

**Command:** `python -m app.cli.search`

**Purpose:** Test search functionality (FTS5, vector, hybrid).

### Basic Usage

```bash
# Full-text search
python -m app.cli.search "machine learning"

# Vector search
python -m app.cli.search "neural networks" --mode vector

# Hybrid search
python -m app.cli.search "AI ethics" --mode hybrid
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `query` | string | - | Search query (positional argument) |
| `--mode` | string | fts | Search mode (fts, vector, hybrid) |
| `--limit` | int | 10 | Max results to return |
| `--min-score` | float | 0.0 | Minimum relevance score (0.0-1.0) |
| `--rerank` | flag | false | Apply reranking to results |
| `--lang` | string | auto | Filter by language (en, ru, auto) |
| `--output-format` | string | table | Output format (table, json, compact) |

### Examples

**Full-Text Search:**

```bash
python -m app.cli.search "python tutorial" --limit 5

# Output (table format):
# Rank | Score | Title                | URL
# -----|-------|----------------------|-----
#  1   | 0.95  | Python Tutorial 2026 | https://...
#  2   | 0.87  | Learn Python Fast    | https://...
#  ...
```

**Vector Search with Reranking:**

```bash
python -m app.cli.search "deep learning frameworks" \
  --mode vector \
  --rerank \
  --limit 10
```

**Hybrid Search (JSON Output):**

```bash
python -m app.cli.search "AI alignment" \
  --mode hybrid \
  --output-format json | jq '.results[].title'
```

**Filter by Language:**

```bash
python -m app.cli.search "машинное обучение" --lang ru
```

### Search Modes

**FTS (Full-Text Search):**

- SQLite FTS5 index on `topic_search_index` table
- Fastest (1-5ms)
- Best for exact keyword matches

**Vector:**

- ChromaDB vector search on `summary_embeddings`
- Slower (50-200ms)
- Best for semantic similarity

**Hybrid:**

- Combines FTS + Vector results
- Slowest (100-300ms)
- Best for comprehensive search

---

## Search Comparison

**Command:** `python -m app.cli.search_compare`

**Purpose:** Compare FTS vs Vector vs Hybrid search quality.

### Basic Usage

```bash
# Compare all search modes
python -m app.cli.search_compare "query1" "query2" "query3"

# Run with test queries from file
python -m app.cli.search_compare --queries-file test_queries.txt
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `queries` | list | - | Queries to test (positional arguments) |
| `--queries-file` | string | - | File with queries (one per line) |
| `--output-csv` | string | - | Save comparison to CSV file |
| `--limit` | int | 10 | Results per query |

### Examples

**Compare Search Modes:**

```bash
python -m app.cli.search_compare \
  "machine learning" \
  "neural networks" \
  "AI ethics"

# Output:
# Query: machine learning
# FTS:    10 results, avg score: 0.82, top: "ML Tutorial 2026"
# Vector: 10 results, avg score: 0.91, top: "Understanding ML"
# Hybrid: 10 results, avg score: 0.88, top: "ML Tutorial 2026"
# ---
# [similar output for other queries]
```

**Export to CSV:**

```bash
python -m app.cli.search_compare \
  --queries-file queries.txt \
  --output-csv comparison.csv

# comparison.csv columns:
# query, mode, rank, score, title, url
```

**Benchmark Performance:**

```bash
time python -m app.cli.search_compare \
  "query1" "query2" "query3" "query4" "query5"

# Outputs:
# FTS:    avg 3.2ms per query
# Vector: avg 125ms per query
# Hybrid: avg 180ms per query
```

---

## Backfill Embeddings

**Command:** `python -m app.cli.backfill_embeddings`

**Purpose:** Generate embeddings for existing summaries.

### Basic Usage

```bash
# Backfill all summaries missing embeddings
python -m app.cli.backfill_embeddings

# Rebuild all embeddings (even if existing)
python -m app.cli.backfill_embeddings --rebuild
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--rebuild` | flag | false | Regenerate all embeddings (skip existing check) |
| `--batch-size` | int | 50 | Embeddings per batch |
| `--model` | string | (from env) | Override embedding model |
| `--limit` | int | - | Limit to N summaries (for testing) |

### Examples

**Backfill Missing Embeddings:**

```bash
python -m app.cli.backfill_embeddings

# Output:
# Found 1234 summaries
# 456 already have embeddings (skipping)
# Generating embeddings for 778 summaries...
# Batch 1/16: 50 embeddings (3.2s)
# Batch 2/16: 50 embeddings (3.1s)
# ...
# Done! Generated 778 embeddings in 2m34s
```

**Rebuild All:**

```bash
python -m app.cli.backfill_embeddings --rebuild

# Output:
# Rebuilding ALL embeddings (1234 summaries)
# This will take approximately 10 minutes.
# Continue? [y/N] y
# ...
```

**Test on Small Batch:**

```bash
python -m app.cli.backfill_embeddings --limit 10

# Output:
# Generating embeddings for 10 summaries (test mode)
# Done! Generated 10 embeddings in 4.2s
```

### Performance

**Typical Speed:**

- CPU (all-MiniLM-L6-v2): ~50 embeddings/sec
- GPU (all-MiniLM-L6-v2): ~200 embeddings/sec

**Memory Usage:**

- all-MiniLM-L6-v2: ~100 MB model + ~10 MB per batch
- all-mpnet-base-v2: ~400 MB model + ~20 MB per batch

---

## Backfill ChromaDB

**Command:** `python -m app.cli.backfill_chroma_store`

**Purpose:** Populate ChromaDB vector store with embeddings.

### Basic Usage

```bash
# Backfill all embeddings to ChromaDB
python -m app.cli.backfill_chroma_store

# Rebuild ChromaDB collection (delete and recreate)
python -m app.cli.backfill_chroma_store --rebuild
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--rebuild` | flag | false | Delete and rebuild ChromaDB collection |
| `--batch-size` | int | 100 | Documents per batch |
| `--collection` | string | summaries | ChromaDB collection name |
| `--limit` | int | - | Limit to N summaries (for testing) |

### Examples

**Initial Backfill:**

```bash
python -m app.cli.backfill_chroma_store

# Output:
# Connecting to ChromaDB at localhost:8000...
# Collection 'summaries' has 0 documents
# Found 1234 summaries with embeddings
# Upserting batch 1/13: 100 documents (1.2s)
# Upserting batch 2/13: 100 documents (1.1s)
# ...
# Done! Upserted 1234 documents in 18.4s
```

**Rebuild Collection:**

```bash
python -m app.cli.backfill_chroma_store --rebuild

# Output:
# WARNING: This will DELETE all documents in 'summaries' collection!
# Continue? [y/N] y
# Deleting collection...
# Creating new collection...
# Upserting 1234 documents...
# Done!
```

**Test Connection:**

```bash
python -m app.cli.backfill_chroma_store --limit 1

# Output:
# Connecting to ChromaDB at localhost:8000...
# Connection successful!
# Collection 'summaries' exists
# Upserting 1 document (test mode)
# Success!
```

### Prerequisites

**ChromaDB Server:**

```bash
# Start ChromaDB server first
docker run -d -p 8000:8000 chromadb/chroma

# Or via docker-compose
docker-compose up -d chroma
```

**Environment Variables:**

```bash
CHROMA_HOST=localhost:8000
CHROMA_COLLECTION=summaries
ENABLE_CHROMA=true
```

---

## Add Performance Indexes

**Command:** `python -m app.cli.add_performance_indexes`

**Purpose:** Add database indexes for query optimization.

### Basic Usage

```bash
# Add all recommended indexes
python -m app.cli.add_performance_indexes

# Check which indexes would be added (dry-run)
python -m app.cli.add_performance_indexes --check
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--check` | flag | false | Check which indexes are missing without adding them |
| `--drop-first` | flag | false | Drop existing indexes before recreating (dangerous) |

### Examples

**Check Missing Indexes:**

```bash
python -m app.cli.add_performance_indexes --check

# Output:
# Checking database indexes...
# Missing indexes:
#   idx_requests_user_id (requests.user_id)
#   idx_summaries_created_at (summaries.created_at)
#   idx_llm_calls_request_id (llm_calls.request_id)
# Existing indexes: 12
```

**Add Missing Indexes:**

```bash
python -m app.cli.add_performance_indexes

# Output:
# Adding missing indexes...
# Creating idx_requests_user_id... OK (0.2s)
# Creating idx_summaries_created_at... OK (1.5s)
# Creating idx_llm_calls_request_id... OK (0.8s)
# Done! Added 3 indexes in 2.5s
```

### Recommended Indexes

**Requests Table:**

- `idx_requests_user_id` on `user_id`
- `idx_requests_created_at` on `created_at`
- `idx_requests_dedupe_hash` on `dedupe_hash`

**Summaries Table:**

- `idx_summaries_request_id` on `request_id`
- `idx_summaries_created_at` on `created_at`
- `idx_summaries_url` on `url`

**LLM Calls Table:**

- `idx_llm_calls_request_id` on `request_id`
- `idx_llm_calls_created_at` on `created_at`
- `idx_llm_calls_model` on `model`

**Crawl Results Table:**

- `idx_crawl_results_request_id` on `request_id`

---

## MCP Server

**Command:** `python -m app.cli.mcp_server`

**Purpose:** Start Model Context Protocol (MCP) server for AI agent access.

### Basic Usage

```bash
# Start MCP server (stdio mode)
python -m app.cli.mcp_server

# Start with SSE transport
python -m app.cli.mcp_server --transport sse --port 8080
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--transport` | string | stdio | Transport mode (stdio, sse) |
| `--port` | int | 8080 | Port for SSE transport |
| `--host` | string | 0.0.0.0 | Host for SSE transport |

### Examples

**stdio Mode (Claude Desktop):**

```bash
python -m app.cli.mcp_server

# Add to Claude Desktop config:
# ~/.config/claude/claude_desktop_config.json
{
  "mcpServers": {
    "bite-size-reader": {
      "command": "python",
      "args": ["-m", "app.cli.mcp_server"],
      "cwd": "/path/to/bite-size-reader",
      "env": {
        "DB_PATH": "/path/to/data/app.db"
      }
    }
  }
}
```

**SSE Mode (Web Access):**

```bash
python -m app.cli.mcp_server --transport sse --port 8080

# Server starts at http://localhost:8080
# MCP tools available via HTTP SSE
```

### Available Tools

**Search Tools:**

- `search_summaries` - Search by query
- `get_summary_by_id` - Get summary by ID
- `get_summaries_by_topic` - Filter by topic tag

**Stats Tools:**

- `get_stats` - Database statistics
- `get_user_stats` - User-specific stats

See: [MCP Server Documentation](../mcp_server.md)

---

## Common Patterns

### Debugging Failed Summarization

```bash
# 1. Try CLI runner with debug logging
python -m app.cli.summary \
  --url <URL> \
  --log-level DEBUG

# 2. Check database for errors
sqlite3 data/app.db "SELECT * FROM requests WHERE url = '<URL>';"

# 3. Check LLM calls
sqlite3 data/app.db "SELECT error_message FROM llm_calls WHERE request_id = '<correlation_id>';"
```

### Testing Search Performance

```bash
# 1. Backfill embeddings if missing
python -m app.cli.backfill_embeddings

# 2. Backfill ChromaDB
python -m app.cli.backfill_chroma_store

# 3. Compare search modes
python -m app.cli.search_compare "test query"

# 4. Benchmark
time python -m app.cli.search "test query" --mode vector
```

### Database Maintenance

```bash
# 1. Backup database
cp data/app.db data/app.db.backup.$(date +%Y%m%d)

# 2. Apply migrations
python -m app.cli.migrate_db

# 3. Add performance indexes
python -m app.cli.add_performance_indexes

# 4. Vacuum database
sqlite3 data/app.db "VACUUM;"
```

---

## Environment Variables

**All CLI tools respect these environment variables:**

```bash
# Database
DB_PATH=/data/app.db

# Logging
LOG_LEVEL=INFO         # DEBUG for CLI debugging
LOG_FORMAT=console     # console or json

# ChromaDB
CHROMA_HOST=localhost:8000
CHROMA_COLLECTION=summaries
ENABLE_CHROMA=true

# Embedding Model
CHROMA_EMBEDDING_MODEL=all-MiniLM-L6-v2
CHROMA_DEVICE=cpu      # or cuda

# LLM (for summary CLI)
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=deepseek/deepseek-v3.2
FIRECRAWL_API_KEY=...
```

---

## Exit Codes

**Standard Exit Codes:**

- `0` - Success
- `1` - Validation error (invalid arguments, missing env vars)
- `2` - External service error (Firecrawl, OpenRouter, ChromaDB)
- `3` - Database error (connection failed, query failed)
- `4` - Internal error (unexpected exception)

**Example:**

```bash
python -m app.cli.summary --url invalid-url
echo $?  # 1 (validation error)

python -m app.cli.summary --url https://example.com
echo $?  # 0 (success)
```

---

## See Also

- [How-To Guides](../how-to/) - Step-by-step task guides
- [TROUBLESHOOTING](../TROUBLESHOOTING.md) - Debugging guide
- [Environment Variables](../environment_variables.md) - Configuration reference

---

**Last Updated:** 2026-02-09
