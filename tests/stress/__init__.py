"""Database stress tests for concurrent access patterns.

These tests verify the system's behavior under load:
- Concurrent writers (10 writers, 100 writes each)
- Mixed read/write contention
- Lock contention verification

To run stress tests:
    pytest tests/stress/ -v -m stress --timeout=120
"""
