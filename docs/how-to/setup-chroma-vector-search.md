# How to Setup ChromaDB Vector Search

Enable semantic search with ChromaDB and sentence embeddings.

**Audience:** Operators
**Difficulty:** Intermediate
**Estimated Time:** 15 minutes

---

## What ChromaDB Provides

ChromaDB enables **semantic search** over your summaries:

- **Natural language queries**: "machine learning tutorials" finds relevant articles even if they use different terms
- **Vector embeddings**: Converts text to 384-dimensional vectors using sentence-transformers
- **Similarity search**: Finds semantically similar summaries (not just keyword matches)
- **Hybrid search**: Combines semantic search with full-text search and reranking

**Use case**: Search past summaries by meaning, not just keywords.

---

## Prerequisites

- Bite-Size Reader installed and running
- Python 3.13+ with sentence-transformers support
- 1-2 GB RAM for embedding model

---

## Steps

### 1. Install ChromaDB

**Option A: Docker (Recommended)**

```bash
# Start ChromaDB container
docker run -d \
  --name chromadb \
  -p 8000:8000 \
  -v $(pwd)/chroma_data:/chroma/chroma \
  --restart unless-stopped \
  chromadb/chroma:latest

# Verify running
curl http://localhost:8000/api/v1/heartbeat
# Should return: OK or heartbeat timestamp
```

**Option B: Local Installation**

```bash
# Install chromadb
pip install chromadb

# Start ChromaDB server
chroma run --host localhost --port 8000 --path ./chroma_data

# Or run in background
nohup chroma run --host localhost --port 8000 --path ./chroma_data > chroma.log 2>&1 &
```

---

### 2. Configure Connection

Add to your `.env` file:

```bash
# Enable ChromaDB
ENABLE_CHROMA=true

# ChromaDB server
CHROMA_HOST=localhost
CHROMA_PORT=8000

# Embedding model (default: all-MiniLM-L6-v2)
CHROMA_EMBEDDING_MODEL=all-MiniLM-L6-v2

# Device (cpu or cuda)
CHROMA_DEVICE=cpu

# Collection name
CHROMA_COLLECTION_NAME=summaries
```

---

### 3. Download Embedding Model

The embedding model downloads automatically on first use, but you can pre-download:

```bash
# Pre-download model (optional)
python -c "
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('all-MiniLM-L6-v2')
print('Model downloaded successfully')
"

# Model size: ~90 MB
# Location: ~/.cache/torch/sentence_transformers/
```

---

### 4. Backfill Existing Summaries

```bash
# Backfill embeddings for existing summaries
python -m app.cli.backfill_chroma_store

# Expected output:
# INFO: Found 150 summaries to backfill
# INFO: Processing batch 1/3 (50 summaries)
# INFO: Processing batch 2/3 (50 summaries)
# INFO: Processing batch 3/3 (50 summaries)
# INFO: Backfill complete: 150 summaries

# Verify collection created
curl http://localhost:8000/api/v1/collections
# Should show: "summaries" collection

# Check count
curl http://localhost:8000/api/v1/collections/summaries/count
# Should match summary count in database
```

---

### 5. Restart Bot

```bash
# Docker
docker restart bite-size-reader

# Local
python bot.py
```

---

## Verification

### Test Semantic Search

**Via Telegram Bot:**

```
/search machine learning basics
```

**Via CLI:**

```bash
python -m app.cli.search --query "machine learning basics"
```

**Expected output:**

- Returns semantically related summaries (not just keyword matches)
- Results ranked by relevance (semantic similarity + reranking)
- Fast response (~200-500ms for typical collection)

### Verify ChromaDB

```bash
# Check collection exists
curl http://localhost:8000/api/v1/collections

# Get collection count
curl http://localhost:8000/api/v1/collections/summaries/count

# Query collection directly
curl -X POST http://localhost:8000/api/v1/collections/summaries/query \
  -H "Content-Type: application/json" \
  -d '{
    "query_texts": ["machine learning"],
    "n_results": 5
  }'
```

---

## Troubleshooting

### ChromaDB connection failed

**Symptom:** Warning logs "Failed to connect to ChromaDB"

**Solution:**

```bash
# Check if ChromaDB is running
curl http://localhost:8000/api/v1/heartbeat

# If not running, start it
# Docker:
docker start chromadb

# Local:
chroma run --host localhost --port 8000

# Verify connection settings
grep CHROMA_HOST .env
grep CHROMA_PORT .env
```

---

### Embedding generation errors

**Symptom:** Error "Failed to generate embeddings"

**Causes & Solutions:**

1. **Model not downloaded:**

   ```bash
   # Pre-download model
   python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
   ```

2. **GPU/CUDA issues (if using GPU):**

   ```bash
   # Force CPU mode
   CHROMA_DEVICE=cpu
   ```

3. **Out of memory:**

   ```bash
   # Use smaller model
   CHROMA_EMBEDDING_MODEL=all-MiniLM-L6-v2  # Smallest (90 MB)

   # Or reduce batch size
   CHROMA_BATCH_SIZE=10  # Default: 50
   ```

---

### Collection not found

**Symptom:** Error "Collection 'summaries' does not exist"

**Solution:**

```bash
# Recreate collection and backfill
python -m app.cli.backfill_chroma_store

# Verify collection created
curl http://localhost:8000/api/v1/collections
```

---

### Search returns no results

**Symptom:** Search query returns empty results

**Diagnostics:**

```bash
# Check collection count
curl http://localhost:8000/api/v1/collections/summaries/count
# Should be > 0

# Check database has summaries
sqlite3 data/app.db "SELECT COUNT(*) FROM summaries;"

# If count mismatch, backfill again
python -m app.cli.backfill_chroma_store
```

---

## Advanced Configuration

### Embedding Model Selection

**Small & Fast (Recommended):**

```bash
CHROMA_EMBEDDING_MODEL=all-MiniLM-L6-v2
# Size: 90 MB
# Embedding dim: 384
# Speed: Fast
# Quality: Good
```

**Balanced:**

```bash
CHROMA_EMBEDDING_MODEL=all-mpnet-base-v2
# Size: 420 MB
# Embedding dim: 768
# Speed: Medium
# Quality: Better
```

**Large & Accurate:**

```bash
CHROMA_EMBEDDING_MODEL=all-roberta-large-v1
# Size: 1.4 GB
# Embedding dim: 1024
# Speed: Slow
# Quality: Best
```

---

### GPU Acceleration

```bash
# Enable CUDA (requires NVIDIA GPU)
CHROMA_DEVICE=cuda

# Verify GPU available
python -c "import torch; print(torch.cuda.is_available())"

# Should output: True
```

---

### Distance Metrics

```bash
# Similarity metric (default: cosine)
CHROMA_DISTANCE_METRIC=cosine  # or: l2, ip (inner product)
```

**Recommendations:**

- **Cosine**: Best for semantic search (normalized vectors)
- **L2**: Euclidean distance (faster, but unnormalized)
- **IP**: Inner product (for specific use cases)

---

### Hybrid Search Configuration

```bash
# Enable hybrid search (semantic + full-text)
ENABLE_HYBRID_SEARCH=true

# Semantic search weight (0-1, default: 0.7)
SEMANTIC_SEARCH_WEIGHT=0.7

# Full-text search weight (0-1, default: 0.3)
FULLTEXT_SEARCH_WEIGHT=0.3

# Enable reranking
ENABLE_RERANKING=true
RERANKING_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
```

---

## Performance Tuning

### Memory Optimization

```bash
# Limit ChromaDB memory usage
CHROMA_MAX_MEMORY_MB=512

# Use memory-mapped files (slower but lower RAM)
CHROMA_USE_MMAP=true
```

### Batch Processing

```bash
# Batch size for embedding generation
CHROMA_BATCH_SIZE=50  # Default

# Increase for faster backfill (requires more RAM)
CHROMA_BATCH_SIZE=100

# Decrease if running out of memory
CHROMA_BATCH_SIZE=10
```

### Index Configuration

```bash
# HNSW index parameters (advanced)
CHROMA_HNSW_M=16               # Number of connections per layer
CHROMA_HNSW_EF_CONSTRUCTION=200  # Quality vs speed tradeoff
CHROMA_HNSW_EF_SEARCH=100      # Search-time quality
```

---

## Monitoring

### Collection Statistics

```bash
# Get collection info
curl http://localhost:8000/api/v1/collections/summaries

# Count embeddings
curl http://localhost:8000/api/v1/collections/summaries/count

# Check collection metadata
sqlite3 data/app.db "
  SELECT
    COUNT(*) as total_summaries,
    COUNT(CASE WHEN embedding IS NOT NULL THEN 1 END) as with_embeddings,
    ROUND(AVG(CASE WHEN embedding IS NOT NULL THEN 1.0 ELSE 0.0 END) * 100, 2) as coverage_pct
  FROM summary_embeddings;
"
```

### Search Performance

```bash
# Benchmark search speed
time python -m app.cli.search --query "machine learning"

# Should be < 500ms for collections < 10,000 summaries
```

---

## Maintenance

### Re-index Summaries

```bash
# Rebuild all embeddings (if model changed or collection corrupted)
python -m app.cli.backfill_chroma_store --rebuild

# Incremental update (only new summaries)
python -m app.cli.backfill_chroma_store
```

### Clean Orphaned Embeddings

```bash
# Remove embeddings for deleted summaries
python -m app.cli.cleanup_embeddings
```

### Backup ChromaDB

```bash
# Backup collection data
docker cp chromadb:/chroma/chroma ./chroma_backup

# Or if running locally
cp -r ./chroma_data ./chroma_backup

# Restore from backup
docker cp ./chroma_backup chromadb:/chroma/chroma
# Restart ChromaDB
docker restart chromadb
```

---

## Disable ChromaDB (Rollback)

```bash
# Set to false in .env
ENABLE_CHROMA=false

# Restart bot
docker restart bite-size-reader

# Bot falls back to full-text search only (SQLite FTS5)
```

---

## See Also

- [FAQ § Search](../FAQ.md#can-i-search-my-summaries)
- [TROUBLESHOOTING § ChromaDB Issues](../TROUBLESHOOTING.md#chromadb-issues)
- [environment_variables.md § ChromaDB](../environment_variables.md)
- [SPEC.md § Search](../SPEC.md) - Search architecture

---

**Last Updated:** 2026-02-09
