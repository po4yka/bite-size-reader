#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
cd "$REPO_ROOT"

if command -v uv >/dev/null 2>&1; then
  PYTHONPATH=. uv run python scripts/migration/generate_m4_interface_fixtures.py --check
  cargo test -p bsr-telegram-runtime --manifest-path rust/Cargo.toml
  PYTHONPATH=. uv run pytest -q \
    tests/test_telegram_runtime_runner.py \
    tests/test_message_router_interface_routing.py
elif [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  PYTHONPATH=. "${REPO_ROOT}/.venv/bin/python" scripts/migration/generate_m4_interface_fixtures.py --check
  cargo test -p bsr-telegram-runtime --manifest-path rust/Cargo.toml
  PYTHONPATH=. "${REPO_ROOT}/.venv/bin/python" -m pytest -q \
    tests/test_telegram_runtime_runner.py \
    tests/test_message_router_interface_routing.py
else
  PYTHONPATH=. python scripts/migration/generate_m4_interface_fixtures.py --check
  cargo test -p bsr-telegram-runtime --manifest-path rust/Cargo.toml
  PYTHONPATH=. python -m pytest -q \
    tests/test_telegram_runtime_runner.py \
    tests/test_message_router_interface_routing.py
fi
