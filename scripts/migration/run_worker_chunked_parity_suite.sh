#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

python scripts/migration/generate_worker_chunked_fixtures.py --check
cargo test -p bsr-worker --test chunked_fixture_parity --manifest-path rust/Cargo.toml
pytest -q tests/test_worker_runtime.py tests/test_content_chunker_worker.py
