"""Chaos tests for circuit breaker functionality.

These tests verify that the circuit breaker properly protects the system
from cascading failures by:
- Opening after repeated failures
- Transitioning to half-open after timeout
- Closing again after successful requests in half-open state
"""

from __future__ import annotations

import asyncio

import pytest

from app.utils.circuit_breaker import CircuitBreaker, CircuitState


class TestCircuitBreakerChaos:
    """Chaos tests for circuit breaker behavior."""

    @pytest.fixture
    def circuit_breaker(self) -> CircuitBreaker:
        """Create a circuit breaker with test-friendly settings."""
        return CircuitBreaker(
            failure_threshold=3,
            timeout=1.0,  # Short timeout for testing
            success_threshold=2,
        )

    def test_circuit_opens_after_repeated_failures(self, circuit_breaker: CircuitBreaker) -> None:
        """Verify circuit opens after failure threshold is reached."""
        # Initially closed
        assert circuit_breaker.state == CircuitState.CLOSED
        assert circuit_breaker.can_proceed()

        # Record failures up to threshold
        for _ in range(3):
            circuit_breaker.record_failure()

        # Circuit should now be open
        assert circuit_breaker.state == CircuitState.OPEN
        assert not circuit_breaker.can_proceed()

    def test_circuit_transitions_to_half_open_after_timeout(
        self, circuit_breaker: CircuitBreaker
    ) -> None:
        """Verify circuit transitions to half-open after timeout."""
        # Open the circuit
        for _ in range(3):
            circuit_breaker.record_failure()

        assert circuit_breaker.state == CircuitState.OPEN

        # Wait for timeout (plus a small buffer)
        import time

        time.sleep(1.2)

        # Should allow a test request (half-open)
        assert circuit_breaker.can_proceed()
        assert circuit_breaker.state == CircuitState.HALF_OPEN

    def test_circuit_closes_after_success_in_half_open(
        self, circuit_breaker: CircuitBreaker
    ) -> None:
        """Verify circuit closes after successful requests in half-open."""
        # Open the circuit
        for _ in range(3):
            circuit_breaker.record_failure()

        # Wait for timeout
        import time

        time.sleep(1.2)

        # First success in half-open
        assert circuit_breaker.can_proceed()
        circuit_breaker.record_success()

        # Second success should close the circuit
        circuit_breaker.record_success()

        assert circuit_breaker.state == CircuitState.CLOSED
        assert circuit_breaker.can_proceed()

    def test_circuit_reopens_on_failure_in_half_open(self, circuit_breaker: CircuitBreaker) -> None:
        """Verify circuit reopens if failure occurs in half-open."""
        # Open the circuit
        for _ in range(3):
            circuit_breaker.record_failure()

        # Wait for timeout
        import time

        time.sleep(1.2)

        # Fail in half-open
        assert circuit_breaker.can_proceed()
        circuit_breaker.record_failure()

        # Should be open again
        assert circuit_breaker.state == CircuitState.OPEN
        assert not circuit_breaker.can_proceed()

    def test_circuit_breaker_stats(self, circuit_breaker: CircuitBreaker) -> None:
        """Verify circuit breaker statistics are accurate."""
        # Record some activity
        circuit_breaker.record_success()
        circuit_breaker.record_success()
        circuit_breaker.record_failure()

        stats = circuit_breaker.get_stats()

        assert stats["state"] == "closed"
        assert stats["failure_count"] == 1
        assert "last_failure_time" in stats

    @pytest.mark.asyncio
    async def test_concurrent_circuit_breaker_access(self) -> None:
        """Verify circuit breaker is thread-safe under concurrent access."""
        cb = CircuitBreaker(failure_threshold=10, timeout=60.0, success_threshold=2)

        async def record_random_outcome():
            import random

            for _ in range(100):
                if random.random() < 0.3:
                    cb.record_failure()
                else:
                    cb.record_success()
                await asyncio.sleep(0.001)

        # Run concurrent tasks
        tasks = [asyncio.create_task(record_random_outcome()) for _ in range(5)]
        await asyncio.gather(*tasks)

        # Should not crash and stats should be consistent
        stats = cb.get_stats()
        assert "state" in stats
        assert "failure_count" in stats


@pytest.mark.chaos
class TestFirecrawlCircuitBreakerIntegration:
    """Integration tests for Firecrawl client circuit breaker."""

    @pytest.mark.asyncio
    async def test_firecrawl_returns_503_when_circuit_open(self) -> None:
        """Verify Firecrawl returns 503 when circuit breaker is open."""
        from app.adapters.external.firecrawl.client import FirecrawlClient
        from app.utils.circuit_breaker import CircuitBreaker

        # Create circuit breaker in open state
        cb = CircuitBreaker(failure_threshold=1, timeout=60.0, success_threshold=1)
        cb.record_failure()  # Open the circuit

        # Create client with open circuit breaker
        client = FirecrawlClient(
            api_key="fc-test-key-that-passes-validation-12345",
            circuit_breaker=cb,
        )

        try:
            # Should return error result without making network call
            result = await client.scrape_markdown("https://example.com")

            assert result.status == "error"
            assert result.http_status == 503
            assert "circuit breaker" in result.error_text.lower()
        finally:
            await client.aclose()


@pytest.mark.chaos
class TestOpenRouterCircuitBreakerIntegration:
    """Integration tests for OpenRouter client circuit breaker."""

    @pytest.mark.asyncio
    async def test_openrouter_returns_error_when_circuit_open(self) -> None:
        """Verify OpenRouter returns error when circuit breaker is open."""
        from app.adapters.openrouter.openrouter_client import OpenRouterClient
        from app.utils.circuit_breaker import CircuitBreaker

        # Create circuit breaker in open state
        cb = CircuitBreaker(failure_threshold=1, timeout=60.0, success_threshold=1)
        cb.record_failure()  # Open the circuit

        # Create client with open circuit breaker
        client = OpenRouterClient(
            api_key="sk-or-v1-test-key-that-passes-validation-1234567890",
            model="gpt-3.5-turbo",
            circuit_breaker=cb,
        )

        try:
            # Should return error result without making network call
            result = await client.chat([{"role": "user", "content": "Hello"}])

            assert result.status == "error"
            assert "circuit breaker" in str(result.error_text).lower()
        finally:
            await client.aclose()
