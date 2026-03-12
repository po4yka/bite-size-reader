#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

cargo test -p bsr-mobile-api -p bsr-interface-router --manifest-path rust/Cargo.toml
cargo check --workspace --manifest-path rust/Cargo.toml
pytest -q tests/test_interface_router_runner.py tests/test_runtime_config_migration_flags.py
