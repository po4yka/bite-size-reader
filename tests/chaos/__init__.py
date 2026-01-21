"""Chaos and failure injection tests.

These tests verify the system's resilience under failure conditions:
- Circuit breaker opens after repeated failures
- Graceful degradation under service outages
- Rate limit handling under load
- Timeout behavior verification

To run chaos tests:
    pytest tests/chaos/ -v -m chaos
"""
