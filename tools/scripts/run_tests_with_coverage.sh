#!/bin/bash
# Script to run tests with coverage reporting

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Running Tests with Coverage ==="
echo ""

# Install lightweight test dependencies if needed
if ! python3 -c "import pytest" 2>/dev/null || ! python3 -c "import coverage" 2>/dev/null; then
    echo "Installing test dependencies from requirements-dev.txt..."
    pip install -r requirements-dev.txt
fi

# Run tests with coverage
echo "Running all tests with coverage..."
python3 -m coverage run -m pytest tests/ -v

# Combine parallel coverage files if present
python3 -m coverage combine || true

# Generate coverage report focused on the heavily tested components
echo ""
echo "=== Coverage Report (focused components) ==="
INCLUDE_FILE="${INCLUDE_FILE:-${SCRIPT_DIR}/coverage_includes.txt}"
if [[ ! -f "${INCLUDE_FILE}" ]]; then
    echo "Include file not found: ${INCLUDE_FILE}" >&2
    exit 1
fi

INCLUDE_PATHS=$(grep -v '^#' "${INCLUDE_FILE}" | grep -v '^$')
python3 -m coverage report --include="${INCLUDE_PATHS//$'\n'/,}" --fail-under=80 --skip-empty

# Generate HTML coverage report
echo ""
echo "Generating HTML coverage report..."
python3 -m coverage html --include="${INCLUDE_PATHS//$'\n'/,}"
echo "HTML report generated in htmlcov/index.html"

echo ""
echo "=== Test Summary ==="
python3 -m pytest tests/ --collect-only -q | tail -1
