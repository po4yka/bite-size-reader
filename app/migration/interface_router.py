from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.migration.cutover_monitor import record_cutover_event

logger = logging.getLogger(__name__)

_ROUTER_BIN_ENV = "INTERFACE_ROUTER_RUST_BIN"


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


def _normalize_for_compare(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 8)
    if isinstance(value, dict):
        return {k: _normalize_for_compare(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [_normalize_for_compare(item) for item in value]
    return value


def _diff_paths(expected: Any, actual: Any, *, limit: int = 8) -> list[str]:
    diffs: list[str] = []

    def _walk(lhs: Any, rhs: Any, path: str) -> None:
        if len(diffs) >= limit:
            return
        if type(lhs) is not type(rhs):
            diffs.append(path or "<root>")
            return
        if isinstance(lhs, dict):
            lhs_keys = set(lhs.keys())
            rhs_keys = set(rhs.keys())
            for key in sorted(lhs_keys | rhs_keys):
                next_path = f"{path}.{key}" if path else str(key)
                if key not in lhs or key not in rhs:
                    diffs.append(next_path)
                    if len(diffs) >= limit:
                        return
                    continue
                _walk(lhs[key], rhs[key], next_path)
                if len(diffs) >= limit:
                    return
            return
        if isinstance(lhs, list):
            if len(lhs) != len(rhs):
                diffs.append(f"{path}.length" if path else "length")
                return
            for idx, (lhs_item, rhs_item) in enumerate(zip(lhs, rhs, strict=True)):
                next_path = f"{path}[{idx}]" if path else f"[{idx}]"
                _walk(lhs_item, rhs_item, next_path)
                if len(diffs) >= limit:
                    return
            return
        if lhs != rhs:
            diffs.append(path or "<root>")

    _walk(_normalize_for_compare(expected), _normalize_for_compare(actual), "")
    return diffs


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
    sample_rate: float = 0.0
    timeout_ms: int = 150
    emit_match_logs: bool = False
    max_diffs: int = 8


class InterfaceRouterRunner:
    """M4 canary runner for mobile API and Telegram command routing."""

    def __init__(self, runtime_cfg: Any) -> None:
        self.options = InterfaceRouterRuntimeOptions(
            backend=str(getattr(runtime_cfg, "migration_interface_backend", "rust"))
            .strip()
            .lower(),
            sample_rate=float(getattr(runtime_cfg, "migration_interface_sample_rate", 0.0)),
            timeout_ms=int(getattr(runtime_cfg, "migration_interface_timeout_ms", 150)),
            emit_match_logs=bool(
                getattr(runtime_cfg, "migration_interface_emit_match_logs", False)
            ),
            max_diffs=int(getattr(runtime_cfg, "migration_interface_max_diffs", 8)),
        )

    def _normalized_backend(self) -> str:
        if self.options.backend in {"python", "canary", "rust"}:
            return self.options.backend
        return "python"

    def _should_sample(self, key: str) -> bool:
        rate = self.options.sample_rate
        if rate <= 0.0:
            return False
        if rate >= 1.0:
            return True
        digest = hashlib.sha256(key.encode("utf-8")).digest()[:8]
        normalized = int.from_bytes(digest, byteorder="big") / float(2**64 - 1)
        return normalized <= rate

    def _log_compare(
        self,
        *,
        surface: str,
        correlation_id: str | None,
        diffs: list[str],
    ) -> None:
        if diffs:
            logger.warning(
                "m4_interface_router_mismatch",
                extra={"surface": surface, "cid": correlation_id, "diff_paths": diffs},
            )
            return
        if self.options.emit_match_logs:
            logger.info(
                "m4_interface_router_match", extra={"surface": surface, "cid": correlation_id}
            )

    async def resolve_mobile_route(
        self,
        *,
        method: str,
        path: str,
        correlation_id: str | None = None,
        actor_key: str | None = None,
    ) -> MobileRouteDecision:
        expected = build_python_mobile_route_decision(method, path)
        backend = self._normalized_backend()
        if backend == "python":
            return expected

        if backend == "canary" and not self._should_sample(
            f"mobile:{method}:{path}:{actor_key or correlation_id or ''}"
        ):
            return expected

        try:
            actual_payload = await asyncio.to_thread(
                run_rust_interface_command,
                "mobile-route",
                {"method": method, "path": path},
                timeout_ms=self.options.timeout_ms,
            )
        except Exception as exc:
            logger.warning(
                "m4_interface_router_error",
                extra={"surface": "mobile", "cid": correlation_id, "error": str(exc)},
            )
            record_cutover_event(
                event_type="python_fallback",
                surface="interface_mobile_route",
                reason="rust_backend_failed",
                correlation_id=correlation_id,
                metadata={"backend": backend},
            )
            return expected

        actual = MobileRouteDecision.from_mapping(actual_payload)
        diffs = _diff_paths(
            expected.to_mapping(), actual.to_mapping(), limit=self.options.max_diffs
        )
        self._log_compare(surface="mobile", correlation_id=correlation_id, diffs=diffs)
        return actual

    async def resolve_telegram_command(
        self,
        *,
        text: str,
        correlation_id: str | None = None,
        actor_key: str | None = None,
    ) -> TelegramCommandDecision:
        expected = build_python_telegram_command_decision(text)
        backend = self._normalized_backend()
        if backend == "python":
            return expected

        if backend == "canary" and not self._should_sample(
            f"telegram:{text}:{actor_key or correlation_id or ''}"
        ):
            return expected

        try:
            actual_payload = await asyncio.to_thread(
                run_rust_interface_command,
                "telegram-command",
                {"text": text},
                timeout_ms=self.options.timeout_ms,
            )
        except Exception as exc:
            logger.warning(
                "m4_interface_router_error",
                extra={"surface": "telegram", "cid": correlation_id, "error": str(exc)},
            )
            record_cutover_event(
                event_type="python_fallback",
                surface="interface_telegram_command",
                reason="rust_backend_failed",
                correlation_id=correlation_id,
                metadata={"backend": backend},
            )
            return expected

        actual = TelegramCommandDecision.from_mapping(actual_payload)
        diffs = _diff_paths(
            expected.to_mapping(), actual.to_mapping(), limit=self.options.max_diffs
        )
        self._log_compare(surface="telegram", correlation_id=correlation_id, diffs=diffs)
        return actual
