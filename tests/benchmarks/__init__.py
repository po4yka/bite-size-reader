"""Performance benchmark tests.

These tests measure the performance of critical operations to ensure
they meet required throughput and latency targets.

To run benchmarks:
    pytest tests/benchmarks/ -v --benchmark-enable

Targets:
- URL normalization: >10k ops/sec
- JSON validation: p99 < 10ms
- Database queries: p99 < 100ms
"""
