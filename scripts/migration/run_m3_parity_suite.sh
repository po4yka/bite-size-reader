#!/usr/bin/env bash
set -euo pipefail

if [[ -x ".venv/bin/python" ]]; then
  PYTHON=.venv/bin/python
else
  PYTHON=python
fi

PYTHONPATH=. "$PYTHON" scripts/migration/generate_m3_shadow_fixtures.py --check
cargo test -p bsr-pipeline-shadow --manifest-path rust/Cargo.toml
PYTHONPATH=. "$PYTHON" -m pytest -q \
  tests/test_pipeline_shadow_runner.py::test_pipeline_shadow_runner_executes_real_rust_binary
