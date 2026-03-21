"""Domain events for rule engine state changes.

Events represent things that have happened in the domain and can be
used to trigger side effects or notify other parts of the system.
"""

from dataclasses import dataclass

from app.domain.events.summary_events import DomainEvent


@dataclass(frozen=True)
class RuleExecuted(DomainEvent):
    """Event raised when a rule is executed against an event."""

    rule_id: int
    summary_id: int | None
    event_type: str
    matched: bool
    actions_count: int
    user_id: int

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.rule_id <= 0:
            msg = "rule_id must be positive"
            raise ValueError(msg)
        if self.user_id <= 0:
            msg = "user_id must be positive"
            raise ValueError(msg)


@dataclass(frozen=True)
class RuleError(DomainEvent):
    """Event raised when a rule fails during execution."""

    rule_id: int
    event_type: str
    error_message: str
    user_id: int

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.rule_id <= 0:
            msg = "rule_id must be positive"
            raise ValueError(msg)
        if self.user_id <= 0:
            msg = "user_id must be positive"
            raise ValueError(msg)
        if not self.error_message:
            msg = "error_message cannot be empty"
            raise ValueError(msg)
