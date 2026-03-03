#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if command -v uv >/dev/null 2>&1; then
  RUNNER=(uv run)
else
  RUNNER=()
fi

echo "==> Running characterization gate tests"
"${RUNNER[@]}" pytest \
  tests/characterization/test_immediate_backlog.py \
  tests/characterization/test_auth_sync_characterization.py \
  -v

if command -v desloppify >/dev/null 2>&1; then
  echo "==> Running desloppify migration-readiness snapshot"
  desloppify scan --path .
  desloppify status
else
  echo "==> Skipping desloppify checks (not installed in current environment)"
fi
