#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
cd "$REPO_ROOT"

if command -v uv >/dev/null 2>&1; then
  PYTHONPATH=. uv run python scripts/migration/generate_processing_orchestrator_fixtures.py --check
  cargo test -p bsr-processing-orchestrator --manifest-path rust/Cargo.toml
  PYTHONPATH=. uv run pytest -q tests/test_processing_orchestrator_runner.py
elif [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  PYTHONPATH=. "${REPO_ROOT}/.venv/bin/python" scripts/migration/generate_processing_orchestrator_fixtures.py --check
  cargo test -p bsr-processing-orchestrator --manifest-path rust/Cargo.toml
  PYTHONPATH=. "${REPO_ROOT}/.venv/bin/python" -m pytest -q tests/test_processing_orchestrator_runner.py
else
  PYTHONPATH=. python scripts/migration/generate_processing_orchestrator_fixtures.py --check
  cargo test -p bsr-processing-orchestrator --manifest-path rust/Cargo.toml
  PYTHONPATH=. python -m pytest -q tests/test_processing_orchestrator_runner.py
fi
