#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
cd "$REPO_ROOT"

TEST_ARGS=(
  tests/parity/test_migration_parity_contracts.py
  tests/test_summary_contract.py
  tests/test_response_contracts.py
  tests/test_digest_api_service.py
  -v
)

if command -v uv >/dev/null 2>&1; then
  uv run pytest "${TEST_ARGS[@]}"
elif [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  PYTHONPATH=. "${REPO_ROOT}/.venv/bin/python" -m pytest "${TEST_ARGS[@]}"
else
  PYTHONPATH=. python -m pytest "${TEST_ARGS[@]}"
fi
