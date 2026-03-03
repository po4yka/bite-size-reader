#!/usr/bin/env bash
set -euo pipefail

if [[ -x ".venv/bin/python" ]]; then
  PYTHON=.venv/bin/python
else
  PYTHON=python
fi

PYTHONPATH=. "$PYTHON" scripts/migration/generate_m2_contract_fixtures.py --check
cargo test -p bsr-summary-contract --manifest-path rust/Cargo.toml
