"""Model capabilities detection and caching for OpenRouter."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx


class ModelCapabilities:
    """Handles model capability detection and caching."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        http_referer: str | None = None,
        x_title: str | None = None,
        timeout: int = 60,
        capabilities_ttl_sec: int = 3600,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._http_referer = http_referer
        self._x_title = x_title
        self._timeout = timeout
        self._capabilities_ttl_sec = capabilities_ttl_sec
        self._logger = logging.getLogger(__name__)

        # Cache capabilities: which models support structured outputs
        self._structured_supported_models: set[str] | None = None
        self._capabilities_last_load: float = 0.0

        # Known models that support structured outputs (fallback list)
        self._known_structured_models = {
            # OpenAI models
            "openai/gpt-4o",
            "openai/gpt-5",
            "openai/gpt-5-mini",
            "openai/gpt-5-nano",
            # Google models
            "google/gemini-2.5-pro",
            # DeepSeek models (JSON mode support)
            "deepseek/deepseek-v3-0324:free",
            "deepseek/deepseek-v3-0324",
            "deepseek/deepseek-r1:free",
            "deepseek/deepseek-r1",
            # Moonshot AI (Kimi) models
            "moonshotai/kimi-k2:free",
            "moonshotai/kimi-k2",
            "moonshotai/kimi-k2-thinking",
            # Qwen models
            "qwen/qwen3-max",
            "qwen/qwen3-235b-a22b-instruct-2507",
            "qwen/qwen3-next-80b-a3b-thinking",
            "qwen/qwen3-coder-480b-a35b",
            "qwen/qwen3-coder:free",
            # MiniMax models
            "minimax/minimax-m2",
            "minimax/minimax-m2:free",
        }

    def is_reasoning_heavy_model(self, model: str) -> bool:
        """Check if model is reasoning-heavy (like GPT-5 family, DeepSeek R1, Kimi K2 Thinking)."""
        model_lower = model.lower()
        reasoning_indicators = ["gpt-5", "o1", "reasoning", "-r1", "thinking", "deepseek-r1"]
        return any(indicator in model_lower for indicator in reasoning_indicators)

    def get_safe_structured_fallbacks(self) -> list[str]:
        """Get list of models known to support structured outputs reliably."""
        return [
            "deepseek/deepseek-v3-0324:free",  # Free, reliable, excellent performance
            "deepseek/deepseek-r1:free",  # Free, strong reasoning
            "qwen/qwen3-max",  # Flagship model, comprehensive
            "openai/gpt-4o",  # Reliable paid option
            "google/gemini-2.5-pro",  # Alternative paid option
        ]

    def supports_structured_outputs(self, model: str) -> bool:
        """Check if a model supports structured outputs."""
        # Check cached capabilities first
        if self._structured_supported_models:
            return model in self._structured_supported_models

        # Fallback to known models list
        return model in self._known_structured_models

    async def ensure_structured_supported_models(self) -> None:
        """Fetch and cache models supporting structured outputs."""
        now = time.time()
        if (
            self._structured_supported_models is not None
            and (now - self._capabilities_last_load) < self._capabilities_ttl_sec
        ):
            return

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self._http_referer or "https://github.com/your-repo",
            "X-Title": self._x_title or "Bite-Size Reader Bot",
        }

        try:
            limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
            async with httpx.AsyncClient(timeout=self._timeout, limits=limits) as client:
                resp = await client.get(
                    f"{self._base_url}/models?supported_parameters=structured_outputs",
                    headers=headers,
                )
                resp.raise_for_status()
                payload = resp.json()

                models: set[str] = set()
                data_array = []

                if isinstance(payload, dict):
                    if isinstance(payload.get("data"), list):
                        data_array = payload.get("data", [])
                    elif isinstance(payload.get("models"), list):
                        data_array = payload.get("models", [])

                for item in data_array:
                    try:
                        if isinstance(item, dict):
                            model_id = item.get("id") or item.get("name") or item.get("model")
                            if isinstance(model_id, str) and model_id:
                                models.add(model_id)
                    except Exception:
                        continue

                if models:
                    self._structured_supported_models = models
                    self._logger.debug(
                        "structured_outputs_capabilities_loaded",
                        extra={"models_count": len(models)},
                    )
                # Keep existing cache or use known models as fallback
                elif self._structured_supported_models is None:
                    self._structured_supported_models = self._known_structured_models.copy()
                    self._logger.warning(
                        "using_fallback_structured_models",
                        extra={"models_count": len(self._structured_supported_models)},
                    )

                self._capabilities_last_load = now

        except Exception as e:
            self._capabilities_last_load = now
            # Use known models as fallback
            if self._structured_supported_models is None:
                self._structured_supported_models = self._known_structured_models.copy()

            self._logger.warning(
                "openrouter_capabilities_probe_failed",
                extra={"error": str(e), "using_fallback": True},
            )

    async def get_models(self) -> dict[str, Any]:
        """Get available models from OpenRouter API."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self._http_referer or "https://github.com/your-repo",
            "X-Title": self._x_title or "Bite-Size Reader Bot",
        }

        try:
            limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
            async with httpx.AsyncClient(timeout=self._timeout, limits=limits) as client:
                resp = await client.get(f"{self._base_url}/models", headers=headers)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            self._logger.exception("openrouter_models_error", extra={"error": str(e)})
            raise

    async def get_structured_models(self) -> set[str]:
        """Get set of models that support structured outputs."""
        await self.ensure_structured_supported_models()
        return self._structured_supported_models or set()

    def build_model_fallback_list(
        self,
        primary_model: str,
        fallback_models: list[str],
        response_format: dict[str, Any] | None = None,
        enable_structured_outputs: bool = True,
    ) -> list[str]:
        """Build list of models to try, including structured output fallbacks."""
        models_to_try = [primary_model, *fallback_models]

        # Add structured output fallbacks if needed
        if (
            response_format is not None
            and enable_structured_outputs
            and self.is_reasoning_heavy_model(primary_model)
        ):
            safe_models = self.get_safe_structured_fallbacks()
            for safe_model in safe_models:
                if safe_model not in models_to_try:
                    models_to_try.append(safe_model)

        return models_to_try
