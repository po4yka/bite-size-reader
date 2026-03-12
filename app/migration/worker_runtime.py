from __future__ import annotations

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.migration.cutover_monitor import record_cutover_event

_WORKER_BIN_ENV = "WORKER_RUST_BIN"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_rust_worker_binary() -> Path | None:
    configured = os.getenv(_WORKER_BIN_ENV)
    if configured:
        candidate = Path(configured).expanduser().resolve()
        if candidate.is_file():
            return candidate

    root = _repo_root()
    candidates = (
        root / "rust" / "target" / "release" / "bsr-worker",
        root / "rust" / "target" / "debug" / "bsr-worker",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _serialize_request(request: Any) -> dict[str, Any]:
    response_format = getattr(request, "response_format", None)
    if not isinstance(response_format, dict):
        response_format = {}

    return {
        "preset_name": getattr(request, "preset_name", None),
        "messages": list(getattr(request, "messages", []) or []),
        "response_format": response_format,
        "max_tokens": getattr(request, "max_tokens", None),
        "temperature": getattr(request, "temperature", None),
        "top_p": getattr(request, "top_p", None),
        "model_override": getattr(request, "model_override", None),
    }


def _build_worker_payload(
    *,
    request_id: int | None,
    requests: list[Any],
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "requests": [_serialize_request(request) for request in requests],
    }


def _build_chunked_worker_payload(
    *,
    request_id: int | None,
    chunk_requests: list[Any],
    synthesis_request: Any,
    system_prompt: str,
    chosen_lang: str,
    max_concurrent_calls: int,
) -> dict[str, Any]:
    synthesis_payload = _serialize_request(synthesis_request)
    synthesis_payload["system_prompt"] = system_prompt
    synthesis_payload["chosen_lang"] = chosen_lang

    return {
        "request_id": request_id,
        "chunk_requests": [_serialize_request(request) for request in chunk_requests],
        "synthesis": synthesis_payload,
        "max_concurrent_calls": max(1, int(max_concurrent_calls)),
    }


def materialize_worker_llm_result(payload: dict[str, Any]) -> Any:
    return SimpleNamespace(**payload)


def run_rust_worker_command(
    command: str,
    payload: dict[str, Any],
    *,
    timeout_ms: int = 300000,
    binary_path: Path | None = None,
) -> dict[str, Any]:
    binary = binary_path or resolve_rust_worker_binary()
    if binary is None:
        msg = "Rust worker binary not found"
        raise FileNotFoundError(msg)

    process = subprocess.run(
        [str(binary), command],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
        timeout=max(1.0, timeout_ms / 1000.0),
    )
    if process.returncode != 0:
        stderr = (process.stderr or "").strip()
        stdout = (process.stdout or "").strip()
        msg = (
            f"worker rust command failed ({command}, exit={process.returncode}): {stderr or stdout}"
        )
        raise RuntimeError(msg)

    output = (process.stdout or "").strip()
    if not output:
        msg = f"worker rust command returned empty output ({command})"
        raise RuntimeError(msg)

    parsed = json.loads(output)
    if not isinstance(parsed, dict):
        msg = f"worker rust command returned non-object JSON ({command})"
        raise RuntimeError(msg)
    return parsed


@dataclass(frozen=True)
class WorkerRuntimeOptions:
    backend: str = "python"
    timeout_ms: int = 300000


class WorkerRunner:
    def __init__(self, runtime_cfg: Any) -> None:
        self.options = WorkerRuntimeOptions(
            backend=str(getattr(runtime_cfg, "migration_worker_backend", "python")).strip().lower(),
            timeout_ms=int(getattr(runtime_cfg, "migration_worker_timeout_ms", 300000)),
        )

    @property
    def enabled(self) -> bool:
        return self.options.backend == "rust"

    async def execute_url_single_pass(
        self,
        *,
        requests: list[Any],
        correlation_id: str | None = None,
        request_id: int | None = None,
    ) -> dict[str, Any]:
        return await self._execute(
            command="url-single-pass",
            surface="worker_url_single_pass",
            requests=requests,
            correlation_id=correlation_id,
            request_id=request_id,
        )

    async def execute_forward_text(
        self,
        *,
        requests: list[Any],
        correlation_id: str | None = None,
        request_id: int | None = None,
    ) -> dict[str, Any]:
        return await self._execute(
            command="forward-text",
            surface="worker_forward_text",
            requests=requests,
            correlation_id=correlation_id,
            request_id=request_id,
        )

    async def execute_chunked_url(
        self,
        *,
        chunk_requests: list[Any],
        synthesis_request: Any,
        system_prompt: str,
        chosen_lang: str,
        max_concurrent_calls: int,
        correlation_id: str | None = None,
        request_id: int | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            msg = "Rust worker backend is not enabled"
            raise RuntimeError(msg)

        payload = _build_chunked_worker_payload(
            request_id=request_id,
            chunk_requests=chunk_requests,
            synthesis_request=synthesis_request,
            system_prompt=system_prompt,
            chosen_lang=chosen_lang,
            max_concurrent_calls=max_concurrent_calls,
        )
        try:
            return await asyncio.to_thread(
                run_rust_worker_command,
                "chunked-url",
                payload,
                timeout_ms=self.options.timeout_ms,
            )
        except Exception as exc:
            record_cutover_event(
                event_type="rust_failure",
                surface="worker_chunked_url",
                reason="rust_backend_failed",
                correlation_id=correlation_id,
                metadata={"backend": "rust", "request_id": request_id},
            )
            msg = (
                "Rust worker chunked-url failed; Python fallback is disabled for rust backend mode."
            )
            raise RuntimeError(msg) from exc

    async def _execute(
        self,
        *,
        command: str,
        surface: str,
        requests: list[Any],
        correlation_id: str | None,
        request_id: int | None,
    ) -> dict[str, Any]:
        if not self.enabled:
            msg = "Rust worker backend is not enabled"
            raise RuntimeError(msg)

        payload = _build_worker_payload(request_id=request_id, requests=requests)
        try:
            return await asyncio.to_thread(
                run_rust_worker_command,
                command,
                payload,
                timeout_ms=self.options.timeout_ms,
            )
        except Exception as exc:
            record_cutover_event(
                event_type="rust_failure",
                surface=surface,
                reason="rust_backend_failed",
                correlation_id=correlation_id,
                metadata={"backend": "rust", "request_id": request_id},
            )
            msg = (
                f"Rust worker {command} failed; Python fallback is disabled for rust backend mode."
            )
            raise RuntimeError(msg) from exc
