#!/usr/bin/env bash
set -euo pipefail

if [[ -x ".venv/bin/python" ]]; then
  PYTHON=.venv/bin/python
else
  PYTHON=python
fi

bash scripts/migration/run_m2_parity_suite.sh
bash scripts/migration/run_m3_parity_suite.sh
bash scripts/migration/run_m4_parity_suite.sh
PYTHONPATH=. "$PYTHON" -m pytest \
  tests/test_cutover_monitor.py \
  tests/test_rust_summary_contract_backend.py \
  tests/test_interface_router_runner.py
PYTHONPATH=. "$PYTHON" scripts/migration/check_m5_cutover_window.py --allow-missing-file
