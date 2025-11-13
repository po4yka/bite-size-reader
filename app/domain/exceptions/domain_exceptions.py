"""Domain-specific exceptions.

These exceptions represent business rule violations and domain errors.
They should be caught and handled by the application layer.
"""


class DomainException(Exception):
    """Base exception for all domain errors."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        """Initialize domain exception.

        Args:
            message: Human-readable error message.
            details: Optional dictionary with additional error context.
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InvalidRequestError(DomainException):
    """Raised when a request violates business rules."""

    pass


class InvalidSummaryError(DomainException):
    """Raised when a summary violates business rules."""

    pass


class ContentFetchError(DomainException):
    """Raised when content cannot be fetched."""

    pass


class SummaryGenerationError(DomainException):
    """Raised when summary generation fails."""

    pass


class InvalidStateTransitionError(DomainException):
    """Raised when an invalid state transition is attempted."""

    pass


class ResourceNotFoundError(DomainException):
    """Raised when a requested resource does not exist."""

    pass


class DuplicateResourceError(DomainException):
    """Raised when attempting to create a duplicate resource."""

    pass


class ValidationError(DomainException):
    """Raised when domain validation fails."""

    pass
