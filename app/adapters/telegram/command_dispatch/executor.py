# ruff: noqa: TC001,TC003
"""Execution helpers for Telegram command routing."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from .models import CommandDispatchOutcome, SummarizeCommandHandler
from .routes import AliasCommandRoute, TextCommandRoute, UidCommandRoute


async def dispatch_uid_routes(
    route_probe: str,
    routes: tuple[UidCommandRoute, ...],
    *,
    message: Any,
    uid: int,
    correlation_id: str,
    interaction_id: int,
    start_time: float,
) -> bool:
    for route in routes:
        if route_probe.startswith(route.prefix):
            await route.handler(message, uid, correlation_id, interaction_id, start_time)
            return True
    return False


async def dispatch_text_routes(
    route_probe: str,
    routes: tuple[TextCommandRoute, ...],
    *,
    message: Any,
    text: str,
    uid: int,
    correlation_id: str,
    interaction_id: int,
    start_time: float,
) -> bool:
    for route in routes:
        if route_probe.startswith(route.prefix):
            await route.handler(message, text, uid, correlation_id, interaction_id, start_time)
            return True
    return False


async def dispatch_alias_routes(
    route_probe: str,
    routes: tuple[AliasCommandRoute, ...],
    *,
    message: Any,
    text: str,
    uid: int,
    correlation_id: str,
    interaction_id: int,
    start_time: float,
) -> bool:
    for route in routes:
        matched_alias = _match_prefix(route_probe, route.aliases)
        if matched_alias is None:
            continue
        await route.handler(
            message,
            text,
            uid,
            correlation_id,
            interaction_id,
            start_time,
            matched_alias,
        )
        return True
    return False


async def dispatch_summarize_fallback(
    route_probe: str,
    *,
    summarize_prefix: str,
    handler: SummarizeCommandHandler,
    mark_awaiting_user: Callable[[int], Awaitable[None]] | None,
    message: Any,
    text: str,
    uid: int,
    correlation_id: str,
    interaction_id: int,
    start_time: float,
) -> CommandDispatchOutcome:
    if not route_probe.startswith(summarize_prefix):
        return CommandDispatchOutcome(handled=False)

    next_action, _should_continue = await handler(
        message,
        text,
        uid,
        correlation_id,
        interaction_id,
        start_time,
    )
    if next_action == "awaiting_url" and mark_awaiting_user is not None:
        await mark_awaiting_user(uid)
    return CommandDispatchOutcome(handled=True, next_action=next_action)


def _match_prefix(text: str, prefixes: tuple[str, ...]) -> str | None:
    for prefix in prefixes:
        if text.startswith(prefix):
            return prefix
    return None
