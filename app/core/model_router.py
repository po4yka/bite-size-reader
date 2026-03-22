"""Model resolution based on content tier and constraints.

Maps a ``ContentTier`` + content metadata to a concrete OpenRouter model string,
respecting the override priority: vision > long context > content tier > default.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.content_classifier import ContentTier
from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from app.config.llm import ModelRoutingConfig, OpenRouterConfig

logger = get_logger(__name__)


def resolve_model_for_content(
    *,
    tier: ContentTier,
    content_length: int,
    has_images: bool,
    routing_config: ModelRoutingConfig,
    openrouter_config: OpenRouterConfig,
) -> str:
    """Determine the model to use based on content tier and constraints.

    Override priority (highest to lowest):
    1. Vision model (if ``has_images`` -- handled by caller, not here)
    2. Long context model (if content exceeds threshold)
    3. Content-tier model (technical / sociopolitical / default)
    """
    # Long content override
    if content_length > routing_config.long_context_threshold:
        model = routing_config.long_context_model
        reason = "long_context"
        logger.info(
            "model_routed",
            extra={
                "tier": tier.value,
                "resolved_model": model,
                "override_reason": reason,
                "content_length": content_length,
            },
        )
        return model

    # Content-tier selection
    tier_map = {
        ContentTier.TECHNICAL: routing_config.technical_model,
        ContentTier.SOCIOPOLITICAL: routing_config.sociopolitical_model,
        ContentTier.DEFAULT: routing_config.default_model,
    }
    model = tier_map[tier]
    reason = "content_tier"

    logger.info(
        "model_routed",
        extra={
            "tier": tier.value,
            "resolved_model": model,
            "override_reason": reason,
            "content_length": content_length,
        },
    )
    return model


def resolve_fallback_models(routing_config: ModelRoutingConfig) -> tuple[str, ...]:
    """Return the fallback model chain from routing config."""
    return routing_config.fallback_models
