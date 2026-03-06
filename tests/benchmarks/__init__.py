"""Performance benchmark tests.

These tests measure the performance of critical operations to ensure
they meet required throughput and latency targets.

To run benchmarks:
    pytest tests/benchmarks/ -v --benchmark-enable

Targets:
- URL normalization: >10k ops/sec
- JSON validation: estimated p99 < 100ms on shared CI runners
- Database queries: p99 < 100ms
"""
