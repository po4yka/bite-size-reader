# ChromaDB Debugging Scenarios

## 1. Health Check Fails (Chroma Unreachable)

**Symptoms:** `ChromaDB: unreachable` in health check output. Search returns empty. Logs show `chroma_initialization_failed`.

**Diagnosis:**

```bash
# Check if Chroma container is running
docker ps | grep chroma

# Test HTTP connectivity
curl -s http://localhost:8000/api/v1/heartbeat

# Check configured host
grep CHROMA_HOST .env

# Check firewall / port binding
lsof -i :8000
```

**Fixes:**

- Start Chroma container: `docker compose -f ops/docker/docker-compose.yml up -d chroma`
- Fix `CHROMA_HOST` in `.env` (must include scheme: `http://...`)
- If auth enabled, verify `CHROMA_AUTH_TOKEN` is correct
- Check `CHROMA_CONNECTION_TIMEOUT` if network is slow (default: 10s)

## 2. Search Returns Empty Results

**Symptoms:** `ChromaVectorSearchResults(results=[], has_more=False)` despite known indexed content.

**Diagnosis:**

```bash
# Check collection document count
python .claude/skills/working-with-chromadb/scripts/chroma-health-check.py

# Check language of query vs indexed docs
sqlite3 data/app.db "SELECT lang, COUNT(*) FROM summaries GROUP BY lang;"

# Check if embeddings exist in SQLite
sqlite3 data/app.db "SELECT COUNT(*) FROM summary_embeddings;"

# Check similarity threshold -- cosine distance near 1.0 means low similarity
# Try broader query or different language
python .claude/skills/working-with-chromadb/scripts/chroma-search-test.py "test query" --lang en
python .claude/skills/working-with-chromadb/scripts/chroma-search-test.py "test query" --lang ru
```

**Fixes:**

- Language mismatch: query language auto-detection selects a different model than what was used for indexing. Force `--lang` to match indexed language.
- Empty collection: run backfill `python -m app.cli.backfill_chroma_store --db=data/app.db`
- Scope mismatch: verify `CHROMA_USER_SCOPE` and `CHROMA_ENV` match between indexing and querying
- Model mismatch: if embeddings were generated with a different model, force re-index with `--force`

## 3. Embedding Coverage Gap

**Symptoms:** Summaries exist in SQLite but no corresponding Chroma documents. Partial search coverage.

**Diagnosis:**

```bash
# Compare counts
sqlite3 data/app.db "SELECT COUNT(*) as summaries FROM summaries;"
sqlite3 data/app.db "SELECT COUNT(*) as embeddings FROM summary_embeddings;"

# Find summaries without embeddings
sqlite3 data/app.db << 'EOF'
SELECT s.id, s.lang, r.input_url
FROM summaries s
JOIN requests r ON s.request_id = r.id
LEFT JOIN summary_embeddings se ON s.id = se.summary_id
WHERE se.id IS NULL
LIMIT 20;
EOF

# Check Chroma doc count vs SQLite embedding count
python .claude/skills/working-with-chromadb/scripts/chroma-health-check.py
```

**Fixes:**

- Incremental backfill (skips existing): `python -m app.cli.backfill_chroma_store --db=data/app.db`
- Force regeneration: `python -m app.cli.backfill_chroma_store --db=data/app.db --force`
- Limit batch for testing: `python -m app.cli.backfill_chroma_store --db=data/app.db --limit=10`

## 4. Slow Backfill Performance

**Symptoms:** `backfill_chroma_store` takes excessively long. High CPU or memory during embedding generation.

**Diagnosis:**

```bash
# Check total summaries to process
sqlite3 data/app.db "SELECT COUNT(*) FROM summaries;"

# Check current batch size
# Default is 50, configurable via --batch-size

# Check if model is being loaded repeatedly (look for "embedding_model_loaded" in logs)
```

**Fixes:**

- Reduce batch size if memory-constrained: `--batch-size=20`
- Limit scope: `--limit=100` to process in chunks
- Use `--force` only when necessary (regenerating all embeddings is expensive)
- Set `LOG_LEVEL=WARNING` to reduce I/O overhead during large backfills
- First run is slow due to model download; subsequent runs use cached models

## 5. Inconsistent SQLite vs Chroma Counts

**Symptoms:** `summary_embeddings` count differs significantly from Chroma collection `docs` count.

**Diagnosis:**

```bash
# SQLite embedding count
sqlite3 data/app.db "SELECT COUNT(*) FROM summary_embeddings;"

# Chroma doc count (from health check)
python .claude/skills/working-with-chromadb/scripts/chroma-health-check.py

# Check for chunk windows (one summary -> multiple Chroma docs)
sqlite3 data/app.db << 'EOF'
SELECT se.summary_id, se.model_name, LENGTH(se.embedding_blob) as blob_size
FROM summary_embeddings se
ORDER BY se.created_at DESC
LIMIT 10;
EOF
```

**Explanation:** Chroma count can exceed SQLite embedding count because semantic chunking creates multiple Chroma documents per summary (`MetadataBuilder.prepare_chunk_windows_for_upsert()`). Each chunk window gets its own embedding in Chroma but shares one SQLite embedding record.

**Fixes:**

- If Chroma has orphaned documents from deleted summaries, force reconcile: `python -m app.cli.backfill_chroma_store --db=data/app.db --force`
- Check for deleted summaries that still have Chroma entries

## 6. Language-Specific Search Issues

**Symptoms:** English queries work, Russian queries return irrelevant results (or vice versa). Cross-language search misses.

**Diagnosis:**

```bash
# Check language distribution
sqlite3 data/app.db "SELECT lang, COUNT(*) FROM summaries GROUP BY lang;"

# Check which model was used for embeddings
sqlite3 data/app.db "SELECT model_name, COUNT(*) FROM summary_embeddings GROUP BY model_name;"

# Test same query in different languages
python .claude/skills/working-with-chromadb/scripts/chroma-search-test.py "machine learning" --lang en
python .claude/skills/working-with-chromadb/scripts/chroma-search-test.py "machine learning" --lang ru
```

**Explanation:** Language detection (`app/core/lang.py`) determines which model generates the query embedding. If a document was indexed with `en` model but queried with `ru` model, cosine similarity will be poor because the embedding spaces differ.

**Fixes:**

- Ensure consistent language tagging: check `detect_language()` returns expected values
- For mixed-language content, use `auto` (multilingual model) for both indexing and querying
- Re-index with `--force` if model assignment changed
- Cross-language search is inherently limited with language-specific models; use multilingual model for best cross-language results
