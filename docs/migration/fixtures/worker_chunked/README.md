# Worker Chunked Fixtures

These fixtures lock the Python-oracle baseline for chunked URL worker
finalization. They cover the first Rust-owned execution slice after
single-pass URL and forwarded-text support:

- long-article chunk summaries with successful synthesis
- partial chunk failures with aggregate fallback
- synthesis-preferred stability when both chunk drafts and synthesis drafts are valid

Generate or verify the expected outputs with:

```bash
python scripts/migration/generate_worker_chunked_fixtures.py
python scripts/migration/generate_worker_chunked_fixtures.py --check
```

Rust parity is enforced by:

```bash
cargo test -p bsr-worker --test chunked_fixture_parity --manifest-path rust/Cargo.toml
```
