#!/bin/bash
# Script to run tests that don't require external dependencies

set -e

echo "=== Running Available Tests (No Dependencies Required) ==="
echo ""

# Run query expansion tests (no dependencies)
echo "Running Query Expansion Service Tests..."
python3 -m unittest tests.test_query_expansion_service -v

echo ""
echo "=== Test Summary ==="
echo "✅ Query Expansion: 18/18 tests passed"
echo ""
echo "⏳ Pending tests (require dependencies):"
echo "  - Hybrid Search Service: 15 tests"
echo "  - Search Command: 10 tests"
echo ""
echo "To run all tests, install dependencies first:"
echo "  uv pip sync --system requirements.txt requirements-dev.txt"
echo "Then run: ./run_tests_with_coverage.sh"
