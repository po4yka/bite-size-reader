#!/usr/bin/env bash
set -euo pipefail

pytest \
  tests/parity/test_migration_parity_contracts.py \
  tests/test_summary_contract.py \
  tests/test_response_contracts.py \
  tests/test_digest_api_service.py \
  -v
