# DEPRECATED: migrate callers to app/application/services/ or app/infrastructure/.
# Real implementations have been moved; files here are backward-compat re-exports.
# Remaining callers: CLI tools (search.py, backfill_embeddings.py, backfill_chroma_store.py)
# need port adapters built before the duplicate service files can be removed.
# Removal target: once CLI tools are migrated.
