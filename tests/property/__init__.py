"""Property-based tests using Hypothesis.

These tests use generative testing to explore edge cases:
- URL normalization with arbitrary inputs
- JSON validation with malformed data
- Hash determinism verification

To run property tests:
    pytest tests/property/ -v --hypothesis-show-statistics

Requires:
    hypothesis>=6.100.0
"""
