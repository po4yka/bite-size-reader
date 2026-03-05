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

_TELEGRAM_RUNTIME_BIN_ENV = "TELEGRAM_RUNTIME_RUST_BIN"
_NON_COMMAND_CACHE_KEY = "__m6_non_command__"


@dataclass(frozen=True)
class TelegramRuntimeCommandDecision:
    command: str | None
    handled: bool

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> TelegramRuntimeCommandDecision:
        command = payload.get("command")
        return cls(
            command=str(command) if isinstance(command, str) and command else None,
            handled=bool(payload.get("handled", False)),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {"command": self.command, "handled": self.handled}


def _command_route_cache_key(text: str) -> str:
    raw_text = text or ""
    if not raw_text.startswith("/"):
        return _NON_COMMAND_CACHE_KEY
    token = raw_text.split(maxsplit=1)[0]
    return token or _NON_COMMAND_CACHE_KEY


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_rust_telegram_runtime_binary() -> Path | None:
    configured = os.getenv(_TELEGRAM_RUNTIME_BIN_ENV)
    if configured:
        candidate = Path(configured).expanduser().resolve()
        if candidate.is_file():
            return candidate

    root = _repo_root()
    candidates = (
        root / "rust" / "target" / "release" / "bsr-telegram-runtime",
        root / "rust" / "target" / "debug" / "bsr-telegram-runtime",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def run_rust_telegram_runtime_command(
    command: str,
    payload: dict[str, Any],
    *,
    timeout_ms: int = 150,
    binary_path: Path | None = None,
) -> dict[str, Any]:
    binary = binary_path or resolve_rust_telegram_runtime_binary()
    if binary is None:
        msg = "Rust telegram runtime binary not found"
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
        msg = (
            "telegram runtime rust command failed "
            f"({command}, exit={process.returncode}): {stderr or stdout}"
        )
        raise RuntimeError(msg)

    output = (process.stdout or "").strip()
    if not output:
        msg = f"telegram runtime rust command returned empty output ({command})"
        raise RuntimeError(msg)

    parsed = json.loads(output)
    if not isinstance(parsed, dict):
        msg = f"telegram runtime rust command returned non-object JSON ({command})"
        raise RuntimeError(msg)
    return parsed


@dataclass(frozen=True)
class TelegramRuntimeOptions:
    timeout_ms: int = 150


class TelegramRuntimeRunner:
    """M6 command route-decision runner (Rust authoritative, fail-closed)."""

    def __init__(self, runtime_cfg: Any) -> None:
        legacy_backend = getattr(runtime_cfg, "migration_telegram_runtime_backend", None)
        if legacy_backend not in (None, ""):
            logger.warning(
                "m6_telegram_runtime_legacy_backend_toggle_ignored",
                extra={"requested_backend": str(legacy_backend).strip().lower()},
            )
        self.options = TelegramRuntimeOptions(
            timeout_ms=int(getattr(runtime_cfg, "migration_telegram_runtime_timeout_ms", 150)),
        )
        self._cache_max_entries = 1024
        self._command_route_cache: OrderedDict[str, TelegramRuntimeCommandDecision] = OrderedDict()

    def _get_cached_command_route(self, key: str) -> TelegramRuntimeCommandDecision | None:
        cached = self._command_route_cache.get(key)
        if cached is not None:
            self._command_route_cache.move_to_end(key)
        return cached

    def _store_cached_command_route(
        self, key: str, decision: TelegramRuntimeCommandDecision
    ) -> None:
        self._command_route_cache[key] = decision
        self._command_route_cache.move_to_end(key)
        if len(self._command_route_cache) > self._cache_max_entries:
            self._command_route_cache.popitem(last=False)

    async def resolve_command_route(
        self,
        *,
        text: str,
        correlation_id: str | None = None,
        actor_key: str | None = None,
    ) -> TelegramRuntimeCommandDecision:
        _ = actor_key
        cache_key = _command_route_cache_key(text)
        cached = self._get_cached_command_route(cache_key)
        if cached is not None:
            return cached
        rust_input_text = "not-a-command" if cache_key == _NON_COMMAND_CACHE_KEY else cache_key

        try:
            actual_payload = await asyncio.to_thread(
                run_rust_telegram_runtime_command,
                "command-route",
                {"text": rust_input_text},
                timeout_ms=self.options.timeout_ms,
            )
            decision = TelegramRuntimeCommandDecision.from_mapping(actual_payload)
            self._store_cached_command_route(cache_key, decision)
            return decision
        except Exception as exc:
            logger.warning(
                "m6_telegram_runtime_error",
                extra={
                    "surface": "command_route",
                    "cid": correlation_id,
                    "error": str(exc),
                },
            )
            record_cutover_event(
                event_type="rust_failure",
                surface="telegram_runtime_command_route",
                reason="rust_backend_failed",
                correlation_id=correlation_id,
                metadata={"backend": "rust"},
            )
            msg = (
                "Rust telegram runtime command-route failed; "
                "Python fallback is decommissioned for rust backend mode."
            )
            raise RuntimeError(msg) from exc
