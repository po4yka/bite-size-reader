from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from app.migration.cutover_monitor import record_cutover_event

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
) -> dict[str, Any]:
    requested_backend = os.getenv(_BACKEND_ENV, "rust").strip().lower()
    if requested_backend and requested_backend != "rust":
        logger.warning(
            "summary_contract_backend_decommissioned_mode_ignored",
            extra={"requested_backend": requested_backend, "effective_backend": "rust"},
        )

    binary = resolve_rust_binary()
    if binary is None:
        record_cutover_event(
            event_type="rust_failure",
            surface="summary_contract",
            reason="rust_binary_missing",
            metadata={"requested_backend": requested_backend or "rust"},
        )
        msg = (
            "Rust summary-contract binary not found. "
            "Python fallback is decommissioned for this slice."
        )
        raise FileNotFoundError(msg)

    try:
        return run_rust_validate_and_shape_summary(payload, binary_path=binary)
    except Exception as exc:
        record_cutover_event(
            event_type="rust_failure",
            surface="summary_contract",
            reason="rust_backend_failed",
            metadata={"requested_backend": requested_backend or "rust"},
        )
        logger.exception(
            "summary_contract_rust_backend_failed_no_fallback",
            extra={"error": str(exc)},
        )
        raise
