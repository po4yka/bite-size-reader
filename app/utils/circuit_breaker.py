"""Circuit breaker pattern for batch processing."""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failures exceeded threshold, blocking requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreakerOpenError(Exception):
    """Raised when an operation is blocked by an open circuit breaker."""


class CircuitBreaker:
    """Circuit breaker for batch processing with adaptive failure handling.

    This implements the circuit breaker pattern to prevent cascading failures
    when external services are down or experiencing issues.

    States:
    - CLOSED: Normal operation, requests are processed
    - OPEN: Too many failures, requests are blocked
    - HALF_OPEN: Testing recovery, limited requests allowed
    """

    def __init__(
        self,
        failure_threshold: int,
        timeout: float = 60.0,
        success_threshold: int = 3,
    ):
        """Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            timeout: Seconds to wait before entering half-open state
            success_threshold: Successful attempts needed in half-open to close
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.success_threshold = success_threshold

        self.failure_count = 0
        self.success_count = 0
        self.state = CircuitState.CLOSED
        self.opened_at: float | None = None
        self.last_failure_time: float | None = None

    def can_proceed(self) -> bool:
        """Check if requests should be processed.

        Returns:
            True if request can proceed, False if circuit is open
        """
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if timeout has elapsed to enter half-open
            if self.opened_at and time.time() - self.opened_at >= self.timeout:
                logger.info(
                    "circuit_breaker_half_open",
                    extra={
                        "failure_count": self.failure_count,
                        "timeout": self.timeout,
                    },
                )
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0  # Reset success count for testing
                return True

            # Circuit still open, block request
            return False

        # Allow limited requests to test recovery in HALF_OPEN state
        return self.state == CircuitState.HALF_OPEN

    def record_success(self) -> None:
        """Record a successful operation.

        In HALF_OPEN state, this tracks recovery progress.
        """
        self.success_count += 1

        if self.state == CircuitState.HALF_OPEN:
            # Check if we have enough successes to close circuit
            if self.success_count >= self.success_threshold:
                logger.info(
                    "circuit_breaker_closed",
                    extra={
                        "success_count": self.success_count,
                        "threshold": self.success_threshold,
                        "previous_failures": self.failure_count,
                    },
                )
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.opened_at = None
                self.last_failure_time = None

    def record_failure(self) -> None:
        """Record a failed operation.

        Increments failure count and opens circuit if threshold is exceeded.
        """
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            # Failure during recovery, reopen circuit
            logger.warning(
                "circuit_breaker_reopened",
                extra={
                    "failure_count": self.failure_count,
                    "state": "half_open_to_open",
                },
            )
            self.state = CircuitState.OPEN
            self.opened_at = time.time()
            self.success_count = 0
            return

        if self.state == CircuitState.CLOSED:
            # Check if we've exceeded failure threshold
            if self.failure_count >= self.failure_threshold:
                logger.warning(
                    "circuit_breaker_opened",
                    extra={
                        "failure_count": self.failure_count,
                        "threshold": self.failure_threshold,
                    },
                )
                self.state = CircuitState.OPEN
                self.opened_at = time.time()

    def reset(self) -> None:
        """Reset circuit breaker to initial state."""
        logger.info(
            "circuit_breaker_reset",
            extra={
                "previous_state": self.state.value,
                "failure_count": self.failure_count,
            },
        )
        self.failure_count = 0
        self.success_count = 0
        self.state = CircuitState.CLOSED
        self.opened_at = None
        self.last_failure_time = None

    def get_stats(self) -> dict[str, Any]:
        """Get current circuit breaker statistics.

        Returns:
            Dictionary with current state and metrics
        """
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "failure_threshold": self.failure_threshold,
            "success_threshold": self.success_threshold,
            "opened_at": self.opened_at,
            "last_failure_time": self.last_failure_time,
        }

    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute a function protected by the circuit breaker.

        Args:
            func: Async function to execute
            *args: Positional args for func
            **kwargs: Keyword args for func

        Returns:
            Result of func

        Raises:
            CircuitBreakerOpenError: If circuit is open
            Exception: If func fails (and failure is recorded)
        """
        if not self.can_proceed():
            raise CircuitBreakerOpenError(f"Circuit breaker is {self.state.value}")

        try:
            result = await func(*args, **kwargs)
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise
