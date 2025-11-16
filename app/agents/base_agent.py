"""Base agent class defining the common interface for all agents."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

logger = logging.getLogger(__name__)

TOutput = TypeVar("TOutput")
TInput = TypeVar("TInput")


@dataclass
class AgentResult(Generic[TOutput]):
    """Result of an agent execution.

    Attributes:
        success: Whether the agent completed successfully
        output: The output data (if successful)
        error: Error message (if failed)
        metadata: Additional context and metrics
    """

    success: bool
    output: TOutput | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success_result(cls, output: TOutput, **metadata: Any) -> AgentResult[TOutput]:
        """Create a successful result."""
        return cls(success=True, output=output, metadata=metadata)

    @classmethod
    def error_result(cls, error: str, **metadata: Any) -> AgentResult[TOutput]:
        """Create an error result."""
        return cls(success=False, error=error, metadata=metadata)


class BaseAgent(ABC, Generic[TInput, TOutput]):
    """Base class for all agents in the multi-agent system.

    Each agent should:
    - Have a single, well-defined responsibility
    - Validate its inputs and outputs
    - Provide detailed error messages
    - Log important events with correlation IDs
    - Return structured results
    """

    def __init__(self, name: str, correlation_id: str | None = None):
        """Initialize the agent.

        Args:
            name: Human-readable name for this agent
            correlation_id: Optional correlation ID for tracing
        """
        self.name = name
        self.correlation_id = correlation_id or "unknown"
        self.logger = logger

    @abstractmethod
    async def execute(self, input_data: TInput) -> AgentResult[TOutput]:
        """Execute the agent's primary task.

        Args:
            input_data: The input data required by this agent

        Returns:
            AgentResult containing output or error information
        """

    def log_info(self, message: str, **kwargs: Any) -> None:
        """Log an info message with correlation ID."""
        self.logger.info(
            f"[{self.name}] {message}",
            extra={"correlation_id": self.correlation_id, **kwargs},
        )

    def log_warning(self, message: str, **kwargs: Any) -> None:
        """Log a warning with correlation ID."""
        self.logger.warning(
            f"[{self.name}] {message}",
            extra={"correlation_id": self.correlation_id, **kwargs},
        )

    def log_error(self, message: str, **kwargs: Any) -> None:
        """Log an error with correlation ID."""
        self.logger.error(
            f"[{self.name}] {message}",
            extra={"correlation_id": self.correlation_id, **kwargs},
        )
