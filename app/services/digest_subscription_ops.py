"""Backward-compat re-export — real implementation in app/application/services/digest_subscription_ops."""

from app.application.services.digest_subscription_ops import (  # noqa: F401
    subscribe_channel_atomic,
    unsubscribe_channel_atomic,
)
