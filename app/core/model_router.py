"""Model resolution based on content tier and constraints.

Maps a ``ContentTier`` + content metadata to a concrete OpenRouter model string,
respecting the override priority: vision > quick > long context > content tier > default.
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
    1. Vision model (if ``has_images`` and ``routing_config.vision_model`` is set)
    2. Quick model (if content is short and ``routing_config.quick_model`` is set)
    3. Long context model (if token estimate exceeds ``long_context_threshold_tokens``)
    4. Content-tier model (technical / sociopolitical / default)
    """
    estimated_tokens = content_length // 4

    # Vision override (highest priority)
    if has_images and routing_config.vision_model:
        model = routing_config.vision_model
        logger.info(
            "model_routed",
            extra={
                "tier": tier.value,
                "resolved_model": model,
                "override_reason": "vision",
                "content_length": content_length,
                "estimated_tokens": estimated_tokens,
            },
        )
        return model

    # Quick override for short-form content
    if routing_config.quick_model and estimated_tokens <= routing_config.quick_threshold_tokens:
        model = routing_config.quick_model
        logger.info(
            "model_routed",
            extra={
                "tier": tier.value,
                "resolved_model": model,
                "override_reason": "quick",
                "content_length": content_length,
                "estimated_tokens": estimated_tokens,
            },
        )
        return model

    # Long content override
    if estimated_tokens > routing_config.long_context_threshold_tokens:
        model = routing_config.long_context_model
        reason = "long_context"
        logger.info(
            "model_routed",
            extra={
                "tier": tier.value,
                "resolved_model": model,
                "override_reason": reason,
                "content_length": content_length,
                "estimated_tokens": estimated_tokens,
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
            "estimated_tokens": estimated_tokens,
        },
    )
    return model


def resolve_fallback_models(
    routing_config: ModelRoutingConfig,
    *,
    tier: ContentTier | None = None,
) -> tuple[str, ...]:
    """Return the fallback model chain from routing config.

    When ``tier`` is provided and a tier-specific fallback list is configured
    (non-empty), that list is returned. Otherwise the shared ``fallback_models``
    list is used.
    """
    if tier is not None:
        if tier == ContentTier.TECHNICAL and routing_config.technical_fallback_models:
            return routing_config.technical_fallback_models
        if tier == ContentTier.SOCIOPOLITICAL and routing_config.sociopolitical_fallback_models:
            return routing_config.sociopolitical_fallback_models
        if tier == ContentTier.DEFAULT and routing_config.default_fallback_models:
            return routing_config.default_fallback_models
    return routing_config.fallback_models
