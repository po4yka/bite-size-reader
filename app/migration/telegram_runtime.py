from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.migration.cutover_monitor import record_cutover_event
from app.migration.interface_router import build_python_telegram_command_decision

logger = logging.getLogger(__name__)

_TELEGRAM_RUNTIME_BIN_ENV = "TELEGRAM_RUNTIME_RUST_BIN"


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


def _build_python_command_decision(text: str) -> TelegramRuntimeCommandDecision:
    decision = build_python_telegram_command_decision(text=text)
    return TelegramRuntimeCommandDecision(command=decision.command, handled=decision.handled)


@dataclass(frozen=True)
class TelegramRuntimeOptions:
    backend: str = "python"
    timeout_ms: int = 150


class TelegramRuntimeRunner:
    """M6 command route-decision runner (Python rollback, Rust fail-closed)."""

    def __init__(self, runtime_cfg: Any) -> None:
        self.options = TelegramRuntimeOptions(
            backend=str(getattr(runtime_cfg, "migration_telegram_runtime_backend", "python"))
            .strip()
            .lower(),
            timeout_ms=int(getattr(runtime_cfg, "migration_telegram_runtime_timeout_ms", 150)),
        )

    def _normalized_backend(self) -> str:
        backend = self.options.backend
        if backend in {"python", "rust"}:
            return backend

        logger.warning(
            "m6_telegram_runtime_invalid_backend_defaulting_to_python",
            extra={"requested_backend": backend, "effective_backend": "python"},
        )
        return "python"

    async def resolve_command_route(
        self,
        *,
        text: str,
        correlation_id: str | None = None,
        actor_key: str | None = None,
    ) -> TelegramRuntimeCommandDecision:
        backend = self._normalized_backend()
        _ = actor_key

        if backend == "python":
            return _build_python_command_decision(text)

        try:
            actual_payload = await asyncio.to_thread(
                run_rust_telegram_runtime_command,
                "command-route",
                {"text": text},
                timeout_ms=self.options.timeout_ms,
            )
            return TelegramRuntimeCommandDecision.from_mapping(actual_payload)
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
                metadata={"backend": backend},
            )
            msg = (
                "Rust telegram runtime command-route failed; "
                "Python fallback is decommissioned for rust backend mode."
            )
            raise RuntimeError(msg) from exc
