from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.migration.cutover_monitor import record_cutover_event

logger = logging.getLogger(__name__)

_ROUTER_BIN_ENV = "INTERFACE_ROUTER_RUST_BIN"
_NON_COMMAND_CACHE_KEY = "__m4_non_command__"


@dataclass(frozen=True)
class MobileRouteDecision:
    route_key: str
    rate_limit_bucket: str
    requires_auth: bool
    handled: bool

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> MobileRouteDecision:
        return cls(
            route_key=str(payload.get("route_key") or "unknown"),
            rate_limit_bucket=str(payload.get("rate_limit_bucket") or "default"),
            requires_auth=bool(payload.get("requires_auth", False)),
            handled=bool(payload.get("handled", False)),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "route_key": self.route_key,
            "rate_limit_bucket": self.rate_limit_bucket,
            "requires_auth": self.requires_auth,
            "handled": self.handled,
        }


@dataclass(frozen=True)
class TelegramCommandDecision:
    command: str | None
    handled: bool

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> TelegramCommandDecision:
        command = payload.get("command")
        return cls(
            command=str(command) if isinstance(command, str) and command else None,
            handled=bool(payload.get("handled", False)),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {"command": self.command, "handled": self.handled}


def build_python_mobile_route_decision(method: str, path: str) -> MobileRouteDecision:
    normalized_method = (method or "").strip().upper()
    normalized_path = path or "/"

    if normalized_path == "/":
        return MobileRouteDecision("root", "default", False, True)
    if normalized_path == "/health":
        return MobileRouteDecision("health", "default", False, True)
    if normalized_path == "/metrics":
        return MobileRouteDecision("metrics", "default", False, True)
    if normalized_path in {"/docs", "/redoc", "/openapi.json"} or normalized_path.startswith(
        "/static/"
    ):
        return MobileRouteDecision("docs", "default", False, True)

    route_key = "unknown"
    bucket = "default"
    handled = False

    if normalized_path.startswith("/v1/auth"):
        route_key = "auth"
        handled = True
    elif normalized_path.startswith("/v1/collections"):
        route_key = "collections"
        handled = True
    elif normalized_path.startswith("/v1/summaries"):
        route_key = "summaries"
        bucket = "summaries"
        handled = True
    elif normalized_path.startswith("/v1/articles"):
        route_key = "articles"
        handled = True
    elif normalized_path.startswith("/v1/requests"):
        route_key = "requests"
        bucket = "requests"
        handled = True
    elif normalized_path.startswith("/v1/search"):
        route_key = "search"
        bucket = "search"
        handled = True
    elif normalized_path.startswith("/v1/sync"):
        route_key = "sync"
        handled = True
    elif normalized_path.startswith("/v1/user"):
        route_key = "user"
        handled = True
    elif normalized_path.startswith("/v1/system"):
        route_key = "system"
        handled = True
    elif normalized_path.startswith("/v1/proxy"):
        route_key = "proxy"
        handled = True
    elif normalized_path.startswith("/v1/notifications"):
        route_key = "notifications"
        handled = True
    elif normalized_path.startswith("/v1/digest"):
        route_key = "digest"
        handled = True

    requires_auth = False if route_key == "auth" else normalized_path.startswith("/v1/")
    _ = normalized_method
    return MobileRouteDecision(route_key, bucket, requires_auth, handled)


def build_python_telegram_command_decision(text: str) -> TelegramCommandDecision:
    raw_text = text or ""
    if not raw_text.startswith("/"):
        return TelegramCommandDecision(None, False)

    first = raw_text.split(maxsplit=1)[0]
    if not first:
        return TelegramCommandDecision(None, False)

    command_token = first[1:].split("@", 1)[0]
    normalized = f"/{command_token}"

    mapping = {
        "/start": "/start",
        "/help": "/help",
        "/dbinfo": "/dbinfo",
        "/dbverify": "/dbverify",
        "/clearcache": "/clearcache",
        "/finddb": "/finddb",
        "/findlocal": "/finddb",
        "/findweb": "/find",
        "/findonline": "/find",
        "/find": "/find",
        "/summarize_all": "/summarize_all",
        "/summarize": "/summarize",
        "/cancel": "/cancel",
        "/unread": "/unread",
        "/read": "/read",
        "/search": "/search",
        "/sync_karakeep": "/sync_karakeep",
        "/cdigest": "/cdigest",
        "/digest": "/digest",
        "/channels": "/channels",
        "/subscribe": "/subscribe",
        "/unsubscribe": "/unsubscribe",
        "/init_session": "/init_session",
        "/settings": "/settings",
        "/debug": "/debug",
    }
    canonical = mapping.get(normalized)
    return TelegramCommandDecision(canonical, canonical is not None)


def rewrite_command_prefix(text: str, canonical_command: str) -> str:
    stripped = (text or "").strip()
    if not stripped.startswith("/"):
        return text
    parts = stripped.split(maxsplit=1)
    remainder = parts[1] if len(parts) > 1 else ""
    return f"{canonical_command} {remainder}".rstrip()


def _command_cache_key(text: str) -> str:
    raw_text = text or ""
    if not raw_text.startswith("/"):
        return _NON_COMMAND_CACHE_KEY
    token = raw_text.split(maxsplit=1)[0]
    return token or _NON_COMMAND_CACHE_KEY


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_rust_interface_binary() -> Path | None:
    configured = os.getenv(_ROUTER_BIN_ENV)
    if configured:
        candidate = Path(configured).expanduser().resolve()
        if candidate.is_file():
            return candidate

    root = _repo_root()
    candidates = (
        root / "rust" / "target" / "release" / "bsr-interface-router",
        root / "rust" / "target" / "debug" / "bsr-interface-router",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def run_rust_interface_command(
    command: str,
    payload: dict[str, Any],
    *,
    timeout_ms: int = 150,
    binary_path: Path | None = None,
) -> dict[str, Any]:
    binary = binary_path or resolve_rust_interface_binary()
    if binary is None:
        msg = "Rust interface router binary not found"
        raise FileNotFoundError(msg)

    process = subprocess.run(
        [str(binary), command],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
        timeout=max(0.05, timeout_ms / 1000.0),
    )
    if process.returncode != 0:
        stderr = (process.stderr or "").strip()
        stdout = (process.stdout or "").strip()
        msg = f"interface router rust command failed ({command}, exit={process.returncode}): {stderr or stdout}"
        raise RuntimeError(msg)

    output = (process.stdout or "").strip()
    if not output:
        msg = f"interface router rust command returned empty output ({command})"
        raise RuntimeError(msg)

    parsed = json.loads(output)
    if not isinstance(parsed, dict):
        msg = f"interface router rust command returned non-object JSON ({command})"
        raise RuntimeError(msg)
    return parsed


@dataclass(frozen=True)
class InterfaceRouterRuntimeOptions:
    backend: str = "rust"
    timeout_ms: int = 150


class InterfaceRouterRunner:
    """M4 interface router runner (Rust path required)."""

    def __init__(self, runtime_cfg: Any) -> None:
        self.options = InterfaceRouterRuntimeOptions(
            backend=str(getattr(runtime_cfg, "migration_interface_backend", "rust"))
            .strip()
            .lower(),
            timeout_ms=int(getattr(runtime_cfg, "migration_interface_timeout_ms", 150)),
        )
        self._cache_max_entries = 512
        self._mobile_route_cache: OrderedDict[tuple[str, str], MobileRouteDecision] = OrderedDict()
        self._telegram_command_cache: OrderedDict[str, TelegramCommandDecision] = OrderedDict()

    @staticmethod
    def _mobile_route_cache_key(method: str, path: str) -> tuple[str, str]:
        return ((method or "").strip().upper(), path or "/")

    def _get_cached_mobile_route(self, key: tuple[str, str]) -> MobileRouteDecision | None:
        cached = self._mobile_route_cache.get(key)
        if cached is not None:
            self._mobile_route_cache.move_to_end(key)
        return cached

    def _store_cached_mobile_route(
        self, key: tuple[str, str], decision: MobileRouteDecision
    ) -> None:
        self._mobile_route_cache[key] = decision
        self._mobile_route_cache.move_to_end(key)
        if len(self._mobile_route_cache) > self._cache_max_entries:
            self._mobile_route_cache.popitem(last=False)

    def _get_cached_telegram_command(self, key: str) -> TelegramCommandDecision | None:
        cached = self._telegram_command_cache.get(key)
        if cached is not None:
            self._telegram_command_cache.move_to_end(key)
        return cached

    def _store_cached_telegram_command(self, key: str, decision: TelegramCommandDecision) -> None:
        self._telegram_command_cache[key] = decision
        self._telegram_command_cache.move_to_end(key)
        if len(self._telegram_command_cache) > self._cache_max_entries:
            self._telegram_command_cache.popitem(last=False)

    def _normalized_backend(self) -> str:
        backend = self.options.backend
        if backend != "rust":
            logger.warning(
                "m4_interface_router_backend_decommissioned_mode_ignored",
                extra={"requested_backend": backend, "effective_backend": "rust"},
            )
        return "rust"

    async def resolve_mobile_route(
        self,
        *,
        method: str,
        path: str,
        correlation_id: str | None = None,
        actor_key: str | None = None,
    ) -> MobileRouteDecision:
        backend = self._normalized_backend()
        _ = actor_key
        cache_key = self._mobile_route_cache_key(method, path)
        cached = self._get_cached_mobile_route(cache_key)
        if cached is not None:
            return cached

        try:
            actual_payload = await asyncio.to_thread(
                run_rust_interface_command,
                "mobile-route",
                {"method": cache_key[0], "path": cache_key[1]},
                timeout_ms=self.options.timeout_ms,
            )
        except Exception as exc:
            logger.warning(
                "m4_interface_router_error",
                extra={"surface": "mobile", "cid": correlation_id, "error": str(exc)},
            )
            record_cutover_event(
                event_type="rust_failure",
                surface="interface_mobile_route",
                reason="rust_backend_failed",
                correlation_id=correlation_id,
                metadata={"backend": backend},
            )
            msg = "Rust interface mobile-route failed; Python fallback is decommissioned."
            raise RuntimeError(msg) from exc

        decision = MobileRouteDecision.from_mapping(actual_payload)
        self._store_cached_mobile_route(cache_key, decision)
        return decision

    async def resolve_telegram_command(
        self,
        *,
        text: str,
        correlation_id: str | None = None,
        actor_key: str | None = None,
    ) -> TelegramCommandDecision:
        backend = self._normalized_backend()
        _ = actor_key
        cache_key = _command_cache_key(text)
        cached = self._get_cached_telegram_command(cache_key)
        if cached is not None:
            return cached
        rust_input_text = "not-a-command" if cache_key == _NON_COMMAND_CACHE_KEY else cache_key

        try:
            actual_payload = await asyncio.to_thread(
                run_rust_interface_command,
                "telegram-command",
                {"text": rust_input_text},
                timeout_ms=self.options.timeout_ms,
            )
        except Exception as exc:
            logger.warning(
                "m4_interface_router_error",
                extra={"surface": "telegram", "cid": correlation_id, "error": str(exc)},
            )
            record_cutover_event(
                event_type="rust_failure",
                surface="interface_telegram_command",
                reason="rust_backend_failed",
                correlation_id=correlation_id,
                metadata={"backend": backend},
            )
            msg = "Rust interface telegram-command failed; Python fallback is decommissioned."
            raise RuntimeError(msg) from exc

        decision = TelegramCommandDecision.from_mapping(actual_payload)
        self._store_cached_telegram_command(cache_key, decision)
        return decision
