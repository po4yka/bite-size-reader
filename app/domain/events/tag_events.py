"""Domain events for tag-related state changes.

Events represent things that have happened in the domain and can be
used to trigger side effects or notify other parts of the system.
"""

from dataclasses import dataclass

from app.domain.events.summary_events import DomainEvent


@dataclass(frozen=True)
class TagCreated(DomainEvent):
    """Event raised when a new tag is created."""

    tag_id: int
    user_id: int
    name: str

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.tag_id <= 0:
            msg = "tag_id must be positive"
            raise ValueError(msg)
        if self.user_id <= 0:
            msg = "user_id must be positive"
            raise ValueError(msg)
        if not self.name:
            msg = "name cannot be empty"
            raise ValueError(msg)


@dataclass(frozen=True)
class TagAttached(DomainEvent):
    """Event raised when a tag is attached to a summary."""

    summary_id: int
    tag_id: int
    user_id: int
    source: str

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.summary_id <= 0:
            msg = "summary_id must be positive"
            raise ValueError(msg)
        if self.tag_id <= 0:
            msg = "tag_id must be positive"
            raise ValueError(msg)
        if self.user_id <= 0:
            msg = "user_id must be positive"
            raise ValueError(msg)
        if not self.source:
            msg = "source cannot be empty"
            raise ValueError(msg)


@dataclass(frozen=True)
class TagDetached(DomainEvent):
    """Event raised when a tag is detached from a summary."""

    summary_id: int
    tag_id: int
    user_id: int

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.summary_id <= 0:
            msg = "summary_id must be positive"
            raise ValueError(msg)
        if self.tag_id <= 0:
            msg = "tag_id must be positive"
            raise ValueError(msg)
        if self.user_id <= 0:
            msg = "user_id must be positive"
            raise ValueError(msg)


@dataclass(frozen=True)
class TagMerged(DomainEvent):
    """Event raised when multiple tags are merged into a target tag."""

    source_tag_ids: tuple[int, ...]
    target_tag_id: int
    user_id: int

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.source_tag_ids:
            msg = "source_tag_ids cannot be empty"
            raise ValueError(msg)
        if any(tid <= 0 for tid in self.source_tag_ids):
            msg = "all source_tag_ids must be positive"
            raise ValueError(msg)
        if self.target_tag_id <= 0:
            msg = "target_tag_id must be positive"
            raise ValueError(msg)
        if self.user_id <= 0:
            msg = "user_id must be positive"
            raise ValueError(msg)


@dataclass(frozen=True)
class TagDeleted(DomainEvent):
    """Event raised when a tag is deleted."""

    tag_id: int
    user_id: int

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.tag_id <= 0:
            msg = "tag_id must be positive"
            raise ValueError(msg)
        if self.user_id <= 0:
            msg = "user_id must be positive"
            raise ValueError(msg)
