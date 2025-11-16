#!/usr/bin/env python3
import sys

sys.path.append(".")
from app.adapters.external.response_formatter import ResponseFormatter

# Create a mock response formatter
rf = ResponseFormatter()
rf._telegram_client = None

# Test progress messages
test_messages = [
    "🔄 Processing links: 1/5\n████████░░░░░░░░░░░░",
    "🔄 Processing links: 2/5\n██████████░░░░░░░░░░",
    "🔄 Processing links: 3/5\n████████████░░░░░░░░",
    "📄 File accepted. Processing 5 links.",
    "✅ All 5 links have been processed.",
]

for msg in test_messages:
    is_safe, error = rf._is_safe_content(msg)
    status = "✓ PASS" if is_safe else "✗ BLOCKED"
    if not is_safe:
        pass
