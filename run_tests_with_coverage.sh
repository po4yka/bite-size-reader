#!/bin/bash
# Script to run tests with coverage reporting

set -e

echo "=== Running Tests with Coverage ==="
echo ""

# Check if dependencies are installed
if ! python3 -c "import pytest" 2>/dev/null; then
    echo "Error: pytest not installed. Please run:"
    echo "  uv pip sync --system requirements.txt requirements-dev.txt"
    exit 1
fi

if ! python3 -c "import coverage" 2>/dev/null; then
    echo "Error: coverage not installed. Please run:"
    echo "  uv pip sync --system requirements.txt requirements-dev.txt"
    exit 1
fi

# Run tests with coverage
echo "Running all tests with coverage..."
python3 -m coverage run -m pytest tests/ -v

# Generate coverage report
echo ""
echo "=== Coverage Report ==="
python3 -m coverage report --skip-empty

# Generate HTML coverage report
echo ""
echo "Generating HTML coverage report..."
python3 -m coverage html
echo "HTML report generated in htmlcov/index.html"

# Show coverage summary for search-related files
echo ""
echo "=== Search Feature Coverage ==="
python3 -m coverage report --include="app/services/hybrid_search_service.py,app/services/query_expansion_service.py,app/services/embedding_service.py,app/services/vector_search_service.py,app/adapters/telegram/command_processor.py"

echo ""
echo "=== Test Summary ==="
python3 -m pytest tests/ --collect-only -q | tail -1
