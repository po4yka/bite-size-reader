"""Shared DB transaction helpers for digest channel subscriptions."""

from __future__ import annotations

from app.db.models import Channel, ChannelSubscription, _utcnow


def subscribe_channel_atomic(user_id: int, username: str) -> str:
    """Subscribe user to channel within a transaction."""
    channel, _ = Channel.get_or_create(
        username=username,
        defaults={"title": username, "is_active": True},
    )

    existing = (
        ChannelSubscription.select()
        .where(
            ChannelSubscription.user == user_id,
            ChannelSubscription.channel == channel,
        )
        .first()
    )

    if existing:
        if existing.is_active:
            return "already_subscribed"
        existing.is_active = True
        existing.updated_at = _utcnow()
        existing.save()
        return "reactivated"

    ChannelSubscription.create(
        user=user_id,
        channel=channel,
        is_active=True,
    )
    return "created"


def unsubscribe_channel_atomic(user_id: int, username: str) -> str:
    """Unsubscribe user from channel within a transaction."""
    channel = Channel.get_or_none(Channel.username == username)
    if not channel:
        return "not_found"

    sub = (
        ChannelSubscription.select()
        .where(
            ChannelSubscription.user == user_id,
            ChannelSubscription.channel == channel,
            ChannelSubscription.is_active == True,  # noqa: E712
        )
        .first()
    )

    if not sub:
        return "not_subscribed"

    sub.is_active = False
    sub.updated_at = _utcnow()
    sub.save()
    return "unsubscribed"
