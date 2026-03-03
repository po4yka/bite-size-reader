from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import subprocess
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.adapters.content.llm_response_workflow import LLMRequestConfig

logger = logging.getLogger(__name__)

_SHADOW_BIN_ENV = "PIPELINE_SHADOW_RUST_BIN"

_DEFAULT_STATS: dict[str, dict[str, int]] = {
    "extraction_adapter": {"total": 0, "matched": 0, "mismatched": 0, "errors": 0},
    "chunking_preprocess": {"total": 0, "matched": 0, "mismatched": 0, "errors": 0},
    "llm_wrapper_plan": {"total": 0, "matched": 0, "mismatched": 0, "errors": 0},
}

_SHADOW_STATS: dict[str, dict[str, int]] = deepcopy(_DEFAULT_STATS)


def reset_shadow_stats() -> None:
    """Reset process-local shadow counters (primarily for tests)."""
    global _SHADOW_STATS
    _SHADOW_STATS = deepcopy(_DEFAULT_STATS)


def get_shadow_stats_snapshot() -> dict[str, dict[str, int]]:
    """Return a copy of current shadow counters."""
    return deepcopy(_SHADOW_STATS)


def _record_result(slice_name: str, *, matched: bool, had_error: bool = False) -> None:
    stats = _SHADOW_STATS.setdefault(
        slice_name,
        {"total": 0, "matched": 0, "mismatched": 0, "errors": 0},
    )
    stats["total"] += 1
    if matched:
        stats["matched"] += 1
    else:
        stats["mismatched"] += 1
    if had_error:
        stats["errors"] += 1


def build_python_extraction_adapter_snapshot(
    *,
    url_hash: str,
    content_text: str,
    content_source: str | None,
    title: str | None,
    images_count: int,
) -> dict[str, Any]:
    trimmed = (content_text or "").strip()
    content_length = len(trimmed)
    word_count = len(trimmed.split())
    source = (content_source or "unknown").strip().lower() or "unknown"
    title_present = bool((title or "").strip())
    has_media = images_count > 0

    cyrillic = sum(1 for ch in trimmed if "\u0400" <= ch <= "\u04ff")
    latin = sum(1 for ch in trimmed if ch.isascii() and ch.isalpha())
    if cyrillic == 0 and latin == 0:
        language_hint = "unknown"
    elif cyrillic > latin * 1.2:
        language_hint = "ru"
    else:
        language_hint = "en"

    content_fingerprint = hashlib.sha256(trimmed.encode("utf-8")).hexdigest()[:16]
    low_value = content_length < 120 or word_count < 20

    return {
        "url_hash": url_hash,
        "content_length": content_length,
        "word_count": word_count,
        "content_source": source,
        "title_present": title_present,
        "images_count": int(images_count),
        "has_media": has_media,
        "language_hint": language_hint,
        "content_fingerprint": content_fingerprint,
        "low_value": low_value,
    }


def build_python_chunking_preprocess_snapshot(
    *,
    content_text: str,
    enable_chunking: bool,
    max_chars: int,
    long_context_model: str | None,
    should_chunk: bool,
) -> dict[str, Any]:
    content_length = len(content_text)
    safe_max_chars = max(1, int(max_chars))
    chunk_size = max(4000, min(12000, safe_max_chars // 10))
    chunk_candidate = bool(enable_chunking and content_length > safe_max_chars)
    has_long_context_model = bool(
        long_context_model is not None and str(long_context_model).strip()
    )
    long_context_bypass = bool(chunk_candidate and has_long_context_model and not should_chunk)
    estimated_chunk_count = (content_length + chunk_size - 1) // chunk_size if should_chunk else 0
    first_chunk_size = min(content_length, chunk_size) if should_chunk else 0

    return {
        "content_length": content_length,
        "max_chars": safe_max_chars,
        "chunk_size": chunk_size,
        "should_chunk": bool(should_chunk),
        "long_context_bypass": long_context_bypass,
        "estimated_chunk_count": estimated_chunk_count,
        "first_chunk_size": first_chunk_size,
    }


def build_python_chunking_preprocess_snapshot_from_input(
    payload: dict[str, Any],
) -> dict[str, Any]:
    content_text = str(payload.get("content_text") or "")
    enable_chunking = bool(payload.get("enable_chunking"))
    max_chars = int(payload.get("max_chars") or 1)
    long_context_model_raw = payload.get("long_context_model")
    long_context_model = (
        str(long_context_model_raw).strip() if isinstance(long_context_model_raw, str) else None
    )
    if isinstance(long_context_model, str) and not long_context_model:
        long_context_model = None

    chunk_candidate = enable_chunking and len(content_text) > max(1, max_chars)
    should_chunk = bool(chunk_candidate and not long_context_model)

    return build_python_chunking_preprocess_snapshot(
        content_text=content_text,
        enable_chunking=enable_chunking,
        max_chars=max_chars,
        long_context_model=long_context_model,
        should_chunk=should_chunk,
    )


def build_python_llm_wrapper_plan_snapshot_from_requests(
    requests: list[LLMRequestConfig],
) -> dict[str, Any]:
    plan: list[dict[str, Any]] = []
    for request in requests:
        response_format = (
            request.response_format if isinstance(request.response_format, dict) else {}
        )
        response_type = str(response_format.get("type") or "unknown")
        plan.append(
            {
                "preset": request.preset_name or "unknown",
                "model": request.model_override or "",
                "response_type": response_type,
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
                "top_p": request.top_p,
            }
        )

    return {
        "request_count": len(plan),
        "requests": plan,
    }


def build_python_llm_wrapper_plan_snapshot_from_input(
    payload: dict[str, Any],
) -> dict[str, Any]:
    base_model = str(payload.get("base_model") or "")
    schema_response_type = str(payload.get("schema_response_type") or "unknown")
    json_object_response_type = str(payload.get("json_object_response_type") or "json_object")

    requests: list[dict[str, Any]] = [
        {
            "preset": "schema_strict",
            "model": base_model,
            "response_type": schema_response_type,
            "max_tokens": payload.get("max_tokens_schema"),
            "temperature": payload.get("base_temperature"),
            "top_p": payload.get("base_top_p"),
        },
        {
            "preset": "json_object_guardrail",
            "model": base_model,
            "response_type": json_object_response_type,
            "max_tokens": payload.get("max_tokens_json_object"),
            "temperature": payload.get("json_temperature"),
            "top_p": payload.get("json_top_p"),
        },
    ]

    added_flash: set[str] = set()
    flash_candidates: list[str] = []
    flash_model = payload.get("flash_model")
    if isinstance(flash_model, str) and flash_model.strip():
        flash_candidates.append(flash_model.strip())

    for model in payload.get("flash_fallback_models") or []:
        if isinstance(model, str) and model.strip():
            flash_candidates.append(model.strip())

    for model in flash_candidates:
        if not model or model == base_model or model in added_flash:
            continue
        added_flash.add(model)
        requests.append(
            {
                "preset": "json_object_flash",
                "model": model,
                "response_type": json_object_response_type,
                "max_tokens": payload.get("max_tokens_json_object"),
                "temperature": payload.get("json_temperature"),
                "top_p": payload.get("json_top_p"),
            }
        )

    fallback_models = [
        model.strip()
        for model in (payload.get("fallback_models") or [])
        if isinstance(model, str) and model.strip()
    ]
    fallback_model = next((model for model in fallback_models if model != base_model), None)
    if fallback_model and fallback_model not in added_flash:
        requests.append(
            {
                "preset": "json_object_fallback",
                "model": fallback_model,
                "response_type": json_object_response_type,
                "max_tokens": payload.get("max_tokens_json_object"),
                "temperature": payload.get("json_temperature"),
                "top_p": payload.get("json_top_p"),
            }
        )

    return {
        "request_count": len(requests),
        "requests": requests,
    }


def build_rust_llm_wrapper_input_from_requests(
    *,
    base_model: str,
    requests: list[LLMRequestConfig],
    fallback_models: tuple[str, ...] | list[str],
    flash_model: str | None,
    flash_fallback_models: tuple[str, ...] | list[str],
) -> dict[str, Any] | None:
    if len(requests) < 2:
        return None

    schema = requests[0]
    guardrail = requests[1]
    schema_type = (
        schema.response_format.get("type")
        if isinstance(schema.response_format, dict)
        else "unknown"
    )
    guardrail_type = (
        guardrail.response_format.get("type")
        if isinstance(guardrail.response_format, dict)
        else "unknown"
    )

    return {
        "base_model": base_model,
        "schema_response_type": schema_type,
        "json_object_response_type": guardrail_type,
        "max_tokens_schema": schema.max_tokens,
        "max_tokens_json_object": guardrail.max_tokens,
        "base_temperature": schema.temperature,
        "base_top_p": schema.top_p,
        "json_temperature": guardrail.temperature,
        "json_top_p": guardrail.top_p,
        "fallback_models": [m for m in fallback_models if m],
        "flash_model": flash_model,
        "flash_fallback_models": [m for m in flash_fallback_models if m],
    }


def _normalize_for_compare(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 8)
    if isinstance(value, dict):
        return {k: _normalize_for_compare(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [_normalize_for_compare(item) for item in value]
    return value


def _diff_paths(expected: Any, actual: Any, *, base_path: str = "", limit: int = 8) -> list[str]:
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
                _walk(lhs_item, rhs_item, f"{path}[{idx}]" if path else f"[{idx}]")
                if len(diffs) >= limit:
                    return
            return
        if lhs != rhs:
            diffs.append(path or "<root>")

    _walk(_normalize_for_compare(expected), _normalize_for_compare(actual), base_path)
    return diffs


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_rust_shadow_binary() -> Path | None:
    configured = os.getenv(_SHADOW_BIN_ENV)
    if configured:
        candidate = Path(configured).expanduser().resolve()
        if candidate.is_file():
            return candidate

    root = _repo_root()
    candidates = (
        root / "rust" / "target" / "release" / "bsr-pipeline-shadow",
        root / "rust" / "target" / "debug" / "bsr-pipeline-shadow",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def run_rust_shadow_command(
    command: str,
    payload: dict[str, Any],
    *,
    timeout_ms: int = 250,
    binary_path: Path | None = None,
) -> dict[str, Any]:
    binary = binary_path or resolve_rust_shadow_binary()
    if binary is None:
        msg = "Rust pipeline shadow binary not found"
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
        msg = f"pipeline shadow rust command failed ({command}, exit={process.returncode}): {stderr or stdout}"
        raise RuntimeError(msg)

    raw = (process.stdout or "").strip()
    if not raw:
        msg = f"pipeline shadow rust command returned empty output ({command})"
        raise RuntimeError(msg)

    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        msg = f"pipeline shadow rust command returned non-object JSON ({command})"
        raise RuntimeError(msg)
    return parsed


@dataclass(frozen=True)
class PipelineShadowRuntimeOptions:
    enabled: bool = False
    sample_rate: float = 0.0
    emit_match_logs: bool = False
    timeout_ms: int = 250
    max_diffs: int = 8


class PipelineShadowRunner:
    """Run M3 shadow comparisons (Python authoritative, Rust comparison path)."""

    def __init__(self, runtime_cfg: Any) -> None:
        self.options = PipelineShadowRuntimeOptions(
            enabled=bool(getattr(runtime_cfg, "migration_shadow_mode_enabled", False)),
            sample_rate=float(getattr(runtime_cfg, "migration_shadow_mode_sample_rate", 0.0)),
            emit_match_logs=bool(
                getattr(runtime_cfg, "migration_shadow_mode_emit_match_logs", False)
            ),
            timeout_ms=int(getattr(runtime_cfg, "migration_shadow_mode_timeout_ms", 250)),
            max_diffs=int(getattr(runtime_cfg, "migration_shadow_mode_max_diffs", 8)),
        )

    def _should_sample(
        self,
        *,
        slice_name: str,
        correlation_id: str | None,
        request_id: int | None,
    ) -> bool:
        if not self.options.enabled:
            return False

        rate = self.options.sample_rate
        if rate <= 0.0:
            return False
        if rate >= 1.0:
            return True

        key = f"{slice_name}:{correlation_id or ''}:{request_id or ''}"
        digest = hashlib.sha256(key.encode("utf-8")).digest()[:8]
        normalized = int.from_bytes(digest, byteorder="big") / float(2**64 - 1)
        return normalized <= rate

    def _log_match(
        self, slice_name: str, correlation_id: str | None, request_id: int | None
    ) -> None:
        if not self.options.emit_match_logs:
            return
        logger.info(
            "m3_shadow_match",
            extra={"slice": slice_name, "cid": correlation_id, "request_id": request_id},
        )

    def _log_mismatch(
        self,
        *,
        slice_name: str,
        correlation_id: str | None,
        request_id: int | None,
        diffs: list[str],
    ) -> None:
        logger.warning(
            "m3_shadow_mismatch",
            extra={
                "slice": slice_name,
                "cid": correlation_id,
                "request_id": request_id,
                "diff_paths": diffs,
            },
        )

    async def compare_extraction_adapter(
        self,
        *,
        correlation_id: str | None,
        request_id: int | None,
        url_hash: str,
        content_text: str,
        content_source: str | None,
        title: str | None,
        images_count: int,
    ) -> None:
        if not self._should_sample(
            slice_name="extraction_adapter",
            correlation_id=correlation_id,
            request_id=request_id,
        ):
            return

        rust_input = {
            "url_hash": url_hash,
            "content_text": content_text,
            "content_source": content_source,
            "title": title,
            "images_count": int(images_count),
        }
        expected = build_python_extraction_adapter_snapshot(
            url_hash=url_hash,
            content_text=content_text,
            content_source=content_source,
            title=title,
            images_count=images_count,
        )

        await self._compare_slice(
            slice_name="extraction_adapter",
            command="extraction-adapter",
            rust_input=rust_input,
            expected=expected,
            correlation_id=correlation_id,
            request_id=request_id,
        )

    async def compare_chunking_preprocess(
        self,
        *,
        correlation_id: str | None,
        request_id: int | None,
        content_text: str,
        enable_chunking: bool,
        max_chars: int,
        long_context_model: str | None,
        should_chunk: bool,
    ) -> None:
        if not self._should_sample(
            slice_name="chunking_preprocess",
            correlation_id=correlation_id,
            request_id=request_id,
        ):
            return

        rust_input = {
            "content_text": content_text,
            "enable_chunking": bool(enable_chunking),
            "max_chars": int(max_chars),
            "long_context_model": long_context_model,
        }
        expected = build_python_chunking_preprocess_snapshot(
            content_text=content_text,
            enable_chunking=enable_chunking,
            max_chars=max_chars,
            long_context_model=long_context_model,
            should_chunk=should_chunk,
        )

        await self._compare_slice(
            slice_name="chunking_preprocess",
            command="chunking-preprocess",
            rust_input=rust_input,
            expected=expected,
            correlation_id=correlation_id,
            request_id=request_id,
        )

    async def compare_llm_wrapper_plan(
        self,
        *,
        correlation_id: str | None,
        request_id: int | None,
        base_model: str,
        requests: list[LLMRequestConfig],
        fallback_models: tuple[str, ...] | list[str],
        flash_model: str | None,
        flash_fallback_models: tuple[str, ...] | list[str],
    ) -> None:
        if not self._should_sample(
            slice_name="llm_wrapper_plan",
            correlation_id=correlation_id,
            request_id=request_id,
        ):
            return

        rust_input = build_rust_llm_wrapper_input_from_requests(
            base_model=base_model,
            requests=requests,
            fallback_models=fallback_models,
            flash_model=flash_model,
            flash_fallback_models=flash_fallback_models,
        )
        if rust_input is None:
            return

        expected = build_python_llm_wrapper_plan_snapshot_from_requests(requests)

        await self._compare_slice(
            slice_name="llm_wrapper_plan",
            command="llm-wrapper-plan",
            rust_input=rust_input,
            expected=expected,
            correlation_id=correlation_id,
            request_id=request_id,
        )

    async def _compare_slice(
        self,
        *,
        slice_name: str,
        command: str,
        rust_input: dict[str, Any],
        expected: dict[str, Any],
        correlation_id: str | None,
        request_id: int | None,
    ) -> None:
        try:
            actual = await asyncio.to_thread(
                run_rust_shadow_command,
                command,
                rust_input,
                timeout_ms=self.options.timeout_ms,
            )
        except Exception as exc:
            _record_result(slice_name, matched=False, had_error=True)
            logger.warning(
                "m3_shadow_error",
                extra={
                    "slice": slice_name,
                    "cid": correlation_id,
                    "request_id": request_id,
                    "error": str(exc),
                },
            )
            return

        diffs = _diff_paths(expected, actual, limit=self.options.max_diffs)
        if diffs:
            _record_result(slice_name, matched=False)
            self._log_mismatch(
                slice_name=slice_name,
                correlation_id=correlation_id,
                request_id=request_id,
                diffs=diffs,
            )
            return

        _record_result(slice_name, matched=True)
        self._log_match(slice_name, correlation_id, request_id)
