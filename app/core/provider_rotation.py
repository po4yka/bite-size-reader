"""Provider-rotation tracker for OpenRouter.

When the upstream provider rejects a request (content policy, quota,
format incompatibility), OpenRouter wraps the error with
``metadata.provider_name`` identifying the upstream that refused.
Rather than advancing to the next *model* in our fallback chain — which
gives up a capable model and may force an expensive ceiling model into
play — this tracker keeps a per-request, per-model set of providers
already tried and tells the caller to retry the same model with an
updated ``provider_order`` header that excludes the offender, until
the budget cap is reached.

Pure decision module. The caller (OpenRouter chat response handler) is
responsible for actually constructing the ``provider_order`` header and
re-issuing the request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True)
class ProviderRotationDecision:
    advance_model: bool
    excluded_providers: tuple[str, ...]


class ProviderRotationTracker:
    """Per-request tracker for provider rotation."""

    def __init__(
        self,
        *,
        max_rotations_per_model: int = 2,
        audit: Callable[[dict[str, object]], None] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        if max_rotations_per_model < 0:
            raise ValueError("max_rotations_per_model must be >= 0")
        self._max = max_rotations_per_model
        self._audit = audit
        self._correlation_id = correlation_id
        self._excluded: dict[str, list[str]] = {}

    def excluded_providers_for(self, model: str) -> tuple[str, ...]:
        return tuple(self._excluded.get(model, ()))

    def on_provider_rejection(
        self, *, model: str, rejected_provider: str
    ) -> ProviderRotationDecision:
        excluded = self._excluded.setdefault(model, [])

        if len(excluded) >= self._max:
            # Budget exhausted for this model — caller must advance.
            self._emit(
                "openrouter_provider_rotation_exhausted",
                model=model,
                excluded_provider=rejected_provider,
                used_rotations=len(excluded),
            )
            return ProviderRotationDecision(advance_model=True, excluded_providers=tuple(excluded))

        if rejected_provider not in excluded:
            excluded.append(rejected_provider)

        self._emit(
            "openrouter_provider_rotation",
            model=model,
            excluded_provider=rejected_provider,
            used_rotations=len(excluded),
        )
        return ProviderRotationDecision(advance_model=False, excluded_providers=tuple(excluded))

    def _emit(self, event: str, **fields: object) -> None:
        if self._audit is None:
            return
        payload: dict[str, object] = {
            "event": event,
            "max_rotations": self._max,
            "correlation_id": self._correlation_id,
            **fields,
        }
        self._audit(payload)


__all__ = ["ProviderRotationDecision", "ProviderRotationTracker"]
