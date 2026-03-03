from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

_BACKEND_ENV = "SUMMARY_CONTRACT_BACKEND"
_BINARY_ENV = "SUMMARY_CONTRACT_RUST_BIN"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def resolve_rust_binary() -> Path | None:
    configured = os.getenv(_BINARY_ENV)
    if configured:
        candidate = Path(configured).expanduser().resolve()
        if candidate.is_file():
            return candidate

    root = _repo_root()
    candidates = (
        root / "rust" / "target" / "release" / "bsr-summary-contract",
        root / "rust" / "target" / "debug" / "bsr-summary-contract",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def run_rust_validate_and_shape_summary(
    payload: dict[str, Any],
    *,
    binary_path: Path | None = None,
    timeout_sec: float = 8.0,
) -> dict[str, Any]:
    binary = binary_path or resolve_rust_binary()
    if binary is None:
        msg = "Rust summary-contract binary not found"
        raise FileNotFoundError(msg)

    process = subprocess.run(
        [str(binary), "normalize"],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout_sec,
    )

    if process.returncode != 0:
        stderr = (process.stderr or "").strip()
        stdout = (process.stdout or "").strip()
        msg = f"Rust summary-contract failed (exit={process.returncode}): {stderr or stdout}"
        raise RuntimeError(msg)

    output = (process.stdout or "").strip()
    if not output:
        msg = "Rust summary-contract returned empty output"
        raise RuntimeError(msg)

    parsed = json.loads(output)
    if not isinstance(parsed, dict):
        msg = "Rust summary-contract returned non-object JSON"
        raise RuntimeError(msg)
    return parsed


def validate_with_backend(
    payload: dict[str, Any],
    *,
    python_fallback: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    backend = os.getenv(_BACKEND_ENV, "python").strip().lower()

    if backend == "python":
        return python_fallback(payload)

    if backend in {"auto", "rust"}:
        binary = resolve_rust_binary()
        if binary is None:
            if backend == "rust":
                logger.warning(
                    "summary_contract_rust_binary_missing",
                    extra={"backend": backend, "env": _BINARY_ENV},
                )
            return python_fallback(payload)

        try:
            return run_rust_validate_and_shape_summary(payload, binary_path=binary)
        except Exception as exc:
            logger.warning(
                "summary_contract_rust_backend_failed",
                extra={"backend": backend, "error": str(exc)},
            )
            return python_fallback(payload)

    logger.warning(
        "summary_contract_unknown_backend",
        extra={"backend": backend, "supported": ["python", "auto", "rust"]},
    )
    return python_fallback(payload)
