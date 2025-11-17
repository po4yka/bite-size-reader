#!/bin/bash
# Script to run tests with coverage reporting

set -e

echo "=== Running Tests with Coverage ==="
echo ""

# Install lightweight test dependencies if needed
if ! python3 -c "import pytest" 2>/dev/null || ! python3 -c "import coverage" 2>/dev/null; then
    echo "Installing minimal test dependencies from requirements-tests.txt..."
    pip install -r requirements-tests.txt
fi

# Run tests with coverage
echo "Running all tests with coverage..."
python3 -m coverage run -m pytest tests/ -v

# Combine parallel coverage files if present
python3 -m coverage combine || true

# Generate coverage report focused on the heavily tested components
echo ""
echo "=== Coverage Report (focused components) ==="
INCLUDE_PATHS=$(cat <<'EOF'
app/security/rate_limiter.py
app/utils/progress_tracker.py
app/utils/retry_utils.py
app/utils/message_formatter.py
app/services/query_expansion_service.py
app/services/hybrid_search_service.py
app/services/topic_search_utils.py
app/models/telegram/telegram_chat.py
app/models/telegram/telegram_entity.py
app/models/telegram/telegram_enums.py
app/models/telegram/telegram_user.py
app/db/models.py
EOF
)

python3 -m coverage report --include="${INCLUDE_PATHS//$'\n'/,}" --fail-under=80 --skip-empty

# Generate HTML coverage report
echo ""
echo "Generating HTML coverage report..."
python3 -m coverage html --include="${INCLUDE_PATHS//$'\n'/,}"
echo "HTML report generated in htmlcov/index.html"

echo ""
echo "=== Test Summary ==="
python3 -m pytest tests/ --collect-only -q | tail -1
