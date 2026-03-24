"""Thread-safe mutable wrapper around frozen AppConfig for hot-reload support."""

from __future__ import annotations

import asyncio
import os
import threading
from dataclasses import replace as dc_replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from app.config.settings import AppConfig

logger = get_logger(__name__)

_DEFAULT_MODELS_PATH = "config/models.yaml"


class ConfigHolder:
    """Thread-safe mutable wrapper around frozen AppConfig.

    Delegates attribute access to the underlying AppConfig so existing code
    using ``cfg.openrouter.model`` continues to work when given a ConfigHolder.
    """

    def __init__(self, initial: AppConfig) -> None:
        self._cfg: AppConfig = initial
        self._lock = threading.Lock()

    @property
    def cfg(self) -> AppConfig:
        return self._cfg

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cfg, name)

    def swap(self, new_cfg: AppConfig) -> AppConfig:
        """Atomically replace the config and return the old one."""
        with self._lock:
            old = self._cfg
            self._cfg = new_cfg
            return old


class ConfigReloader:
    """Polls config/models.yaml for changes and hot-reloads model config."""

    def __init__(
        self,
        holder: ConfigHolder,
        poll_interval: float = 30.0,
        models_path: str | None = None,
    ) -> None:
        self._holder = holder
        self._poll_interval = poll_interval
        self._models_path = Path(
            models_path or os.environ.get("MODELS_CONFIG_PATH", _DEFAULT_MODELS_PATH)
        )
        self._last_mtime: float = 0.0
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Start the background polling task."""
        if self._task is not None:
            return
        self._last_mtime = self._get_mtime()
        self._task = asyncio.get_event_loop().create_task(self._poll_loop())
        logger.info("config_reloader_started", extra={"path": str(self._models_path)})

    async def stop(self) -> None:
        """Stop the background polling task."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def reload_now(self) -> bool:
        """Force an immediate reload. Returns True if config changed."""
        return self._try_reload()

    def _get_mtime(self) -> float:
        try:
            return self._models_path.stat().st_mtime
        except OSError:
            return 0.0

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(self._poll_interval)
            try:
                current_mtime = self._get_mtime()
                if current_mtime > self._last_mtime:
                    self._try_reload()
                    self._last_mtime = current_mtime
            except Exception:
                logger.exception("config_reload_poll_error")

    def _try_reload(self) -> bool:
        """Attempt to reload models config. Returns True if changed."""
        from app.config.models_file import load_models_yaml

        new_env = load_models_yaml(self._models_path)
        if not new_env:
            return False

        old_cfg = self._holder.cfg
        changes: dict[str, tuple[str, str]] = {}

        try:
            new_cfg = self._rebuild_config(old_cfg, new_env, changes)
        except Exception:
            logger.exception("config_rebuild_failed")
            return False

        if not changes:
            return False

        self._holder.swap(new_cfg)
        logger.info(
            "models_config_reloaded",
            extra={"changes": {k: {"old": v[0], "new": v[1]} for k, v in changes.items()}},
        )
        return True

    def _rebuild_config(
        self,
        old_cfg: AppConfig,
        new_env: dict[str, str],
        changes: dict[str, tuple[str, str]],
    ) -> AppConfig:
        """Rebuild config sections from new YAML values."""
        or_updates: dict[str, Any] = {}
        rt_updates: dict[str, Any] = {}
        att_updates: dict[str, Any] = {}

        _or_map = {
            "OPENROUTER_MODEL": ("model", old_cfg.openrouter.model),
            "OPENROUTER_FLASH_MODEL": ("flash_model", old_cfg.openrouter.flash_model),
            "OPENROUTER_FALLBACK_MODELS": (
                "fallback_models",
                ",".join(old_cfg.openrouter.fallback_models),
            ),
            "OPENROUTER_FLASH_FALLBACK_MODELS": (
                "flash_fallback_models",
                ",".join(old_cfg.openrouter.flash_fallback_models),
            ),
            "OPENROUTER_LONG_CONTEXT_MODEL": (
                "long_context_model",
                old_cfg.openrouter.long_context_model or "",
            ),
        }
        for env_key, (field, old_val) in _or_map.items():
            if env_key in new_env and new_env[env_key] != str(old_val):
                new_val = new_env[env_key]
                changes[f"openrouter.{field}"] = (str(old_val), new_val)
                if field in ("fallback_models", "flash_fallback_models"):
                    or_updates[field] = tuple(m.strip() for m in new_val.split(",") if m.strip())
                else:
                    or_updates[field] = new_val

        _rt_map = {
            "MODEL_ROUTING_DEFAULT": ("default_model", old_cfg.model_routing.default_model),
            "MODEL_ROUTING_TECHNICAL": ("technical_model", old_cfg.model_routing.technical_model),
            "MODEL_ROUTING_SOCIOPOLITICAL": (
                "sociopolitical_model",
                old_cfg.model_routing.sociopolitical_model,
            ),
            "MODEL_ROUTING_LONG_CONTEXT": (
                "long_context_model",
                old_cfg.model_routing.long_context_model,
            ),
            "MODEL_ROUTING_ENABLED": ("enabled", str(old_cfg.model_routing.enabled).lower()),
        }
        for env_key, (field, old_val) in _rt_map.items():
            if env_key in new_env and new_env[env_key] != str(old_val):
                new_val = new_env[env_key]
                changes[f"model_routing.{field}"] = (str(old_val), new_val)
                if field == "enabled":
                    rt_updates[field] = new_val.lower() in ("true", "1", "yes")
                elif field == "fallback_models":
                    rt_updates[field] = tuple(m.strip() for m in new_val.split(",") if m.strip())
                else:
                    rt_updates[field] = new_val

        if "ATTACHMENT_VISION_MODEL" in new_env:
            old_vision = old_cfg.attachment.vision_model
            new_vision = new_env["ATTACHMENT_VISION_MODEL"]
            if new_vision != old_vision:
                changes["attachment.vision_model"] = (old_vision, new_vision)
                att_updates["vision_model"] = new_vision

        new_openrouter = (
            old_cfg.openrouter.model_copy(update=or_updates) if or_updates else old_cfg.openrouter
        )
        new_routing = (
            old_cfg.model_routing.model_copy(update=rt_updates)
            if rt_updates
            else old_cfg.model_routing
        )
        new_attachment = (
            old_cfg.attachment.model_copy(update=att_updates) if att_updates else old_cfg.attachment
        )

        app_updates: dict[str, Any] = {}
        if or_updates:
            app_updates["openrouter"] = new_openrouter
        if rt_updates:
            app_updates["model_routing"] = new_routing
        if att_updates:
            app_updates["attachment"] = new_attachment

        return dc_replace(old_cfg, **app_updates) if app_updates else old_cfg
