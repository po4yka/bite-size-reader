"""Base agent class defining the common interface for all agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.core.logging_utils import get_logger

logger = get_logger(__name__)

TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


class AgentResult(BaseModel, Generic[TOutput]):
    """Result of an agent execution."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool
    output: TOutput | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

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
        self.name = name
        self.correlation_id = correlation_id or "unknown"
        self.logger = logger

    @abstractmethod
    async def execute(self, input_data: TInput) -> AgentResult[TOutput]:
        """Execute the agent's primary task."""

    def _log(self, level: str, message: str, **kwargs: Any) -> None:
        """Emit a structured log entry with agent name and correlation ID."""
        getattr(self.logger, level)(
            f"[{self.name}] {message}",
            extra={"correlation_id": self.correlation_id, **kwargs},
        )

    def log_info(self, message: str, **kwargs: Any) -> None:
        self._log("info", message, **kwargs)

    def log_warning(self, message: str, **kwargs: Any) -> None:
        self._log("warning", message, **kwargs)

    def log_error(self, message: str, **kwargs: Any) -> None:
        self._log("error", message, **kwargs)
