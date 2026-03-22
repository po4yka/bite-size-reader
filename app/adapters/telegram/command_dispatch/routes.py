# ruff: noqa: TC001
"""Route dataclasses for Telegram command dispatch."""

from __future__ import annotations

from dataclasses import dataclass

from .models import AliasCommandHandler, TextCommandHandler, UidCommandHandler


@dataclass(frozen=True, slots=True)
class UidCommandRoute:
    prefix: str
    handler: UidCommandHandler


@dataclass(frozen=True, slots=True)
class TextCommandRoute:
    prefix: str
    handler: TextCommandHandler


@dataclass(frozen=True, slots=True)
class AliasCommandRoute:
    aliases: tuple[str, ...]
    handler: AliasCommandHandler


@dataclass(frozen=True, slots=True)
class TelegramCommandRoutes:
    pre_alias_uid: tuple[UidCommandRoute, ...]
    pre_alias_text: tuple[TextCommandRoute, ...]
    local_search_aliases: tuple[AliasCommandRoute, ...]
    online_search_aliases: tuple[AliasCommandRoute, ...]
    pre_summarize_text: tuple[TextCommandRoute, ...]
    summarize_prefix: str
    post_summarize_uid: tuple[UidCommandRoute, ...]
    post_summarize_text: tuple[TextCommandRoute, ...]
    tail_uid: tuple[UidCommandRoute, ...]
