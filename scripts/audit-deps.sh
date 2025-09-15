#!/bin/bash
# Script to run pip-audit while excluding spaCy language models that aren't on PyPI

set -e

echo "🔍 Running security audit (excluding spaCy models)..."

# The spaCy language models (en-core-web-sm, ru-core-news-sm) are installed
# from GitHub releases, not PyPI, so pip-audit cannot audit them.
# We'll audit only the PyPI packages.

echo "Creating filtered requirements files..."

# Filter out spaCy models from requirements files
cat requirements.txt requirements-dev.txt | \
    grep -v "en-core-web-sm" | \
    grep -v "ru-core-news-sm" | \
    sort -u > requirements-audit-filtered.txt

# Add the base spaCy and textacy packages if they're not already there
echo "spacy>=3.7,<4" >> requirements-audit-filtered.txt
echo "textacy>=0.13,<0.14" >> requirements-audit-filtered.txt

echo "📦 Auditing $(wc -l < requirements-audit-filtered.txt) PyPI packages..."

# Run pip-audit on the filtered requirements
pip-audit -r requirements-audit-filtered.txt --strict

# Clean up
rm requirements-audit-filtered.txt

echo "✅ Security audit completed successfully!"
echo "ℹ️  Note: spaCy language models (en-core-web-sm, ru-core-news-sm) are excluded"
echo "   as they are not available on PyPI and cannot be audited."
