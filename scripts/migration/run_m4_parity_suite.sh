#!/usr/bin/env bash
set -euo pipefail

if [[ -x ".venv/bin/python" ]]; then
  PYTHON=.venv/bin/python
else
  PYTHON=python
fi

PYTHONPATH=. "$PYTHON" scripts/migration/generate_m4_interface_fixtures.py --check
cargo test -p bsr-interface-router --manifest-path rust/Cargo.toml
