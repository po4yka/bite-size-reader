from __future__ import annotations

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.lang import LANG_EN, LANG_RU, choose_language, detect_language
from app.migration.cutover_monitor import record_cutover_event
from app.migration.pipeline_shadow import (
    build_python_chunk_sentence_plan_snapshot_from_input,
    build_python_chunking_preprocess_snapshot_from_input,
    build_python_llm_wrapper_plan_snapshot_from_input,
)

_PROCESSING_ORCHESTRATOR_BIN_ENV = "PROCESSING_ORCHESTRATOR_RUST_BIN"
_MAX_SINGLE_PASS_CHARS = 50_000
_MAX_FORWARD_CONTENT_CHARS = 45_000


def _normalize_model(value: Any) -> str:
    return str(value or "").strip()


def _normalize_optional_model(value: Any) -> str | None:
    model = _normalize_model(value)
    return model or None


def _normalize_response_type(value: Any) -> str:
    response_type = str(value or "unknown").strip().lower()
    return response_type or "unknown"


def _estimate_max_chars_for_model(model_name: str | None, base_default: int) -> int:
    if not model_name:
        return int(base_default)
    name = model_name.lower()
    if "gemini-2.5" in name or "2.5-pro" in name or "gemini-2-5" in name:
        return int(1_000_000 * 4 * 0.75)
    return int(base_default)


def _truncate_forward_prompt(prompt: str) -> tuple[str, bool]:
    if len(prompt) <= _MAX_FORWARD_CONTENT_CHARS:
        return prompt, False
    return (
        prompt[:_MAX_FORWARD_CONTENT_CHARS] + "\n\n[Content truncated due to length]",
        True,
    )


def _resolve_forward_source(payload: dict[str, Any]) -> tuple[str, str]:
    chat_title = str(payload.get("source_chat_title") or "").strip()
    if chat_title:
        return "Channel", chat_title

    first_name = str(payload.get("source_user_first_name") or "").strip()
    last_name = str(payload.get("source_user_last_name") or "").strip()
    full_name = f"{first_name} {last_name}".strip()
    if full_name:
        return "Source", full_name

    sender_name = str(payload.get("forward_sender_name") or "").strip()
    return "Source", sender_name


def build_python_url_processing_plan(payload: dict[str, Any]) -> dict[str, Any]:
    content_text = str(payload.get("content_text") or "")
    detected_language = str(payload.get("detected_language") or LANG_EN).strip().lower() or LANG_EN
    preferred_language = str(payload.get("preferred_language") or "auto").strip().lower() or "auto"
    chosen_lang = choose_language(preferred_language, detected_language)
    silent = bool(payload.get("silent"))
    needs_ru_translation = not silent and LANG_RU not in (detected_language, chosen_lang)

    primary_model = _normalize_model(payload.get("primary_model"))
    long_context_model = _normalize_optional_model(payload.get("long_context_model"))
    threshold_model = long_context_model or primary_model
    enable_chunking_raw = payload.get("enable_chunking")
    enable_chunking = enable_chunking_raw if isinstance(enable_chunking_raw, bool) else False
    configured_chunk_max_chars_raw = payload.get("configured_chunk_max_chars")
    configured_chunk_max_chars = (
        configured_chunk_max_chars_raw
        if isinstance(configured_chunk_max_chars_raw, int)
        else 200_000
    )
    configured_chunk_max_chars = max(1, configured_chunk_max_chars)
    tuned_base = max(1, int(configured_chunk_max_chars * 0.8))
    effective_max_chars = _estimate_max_chars_for_model(threshold_model, tuned_base)
    fallback_models_raw = payload.get("fallback_models")
    fallback_models = (
        [model for model in fallback_models_raw if isinstance(model, str)]
        if isinstance(fallback_models_raw, (list, tuple))
        else []
    )
    flash_fallback_models_raw = payload.get("flash_fallback_models")
    flash_fallback_models = (
        [model for model in flash_fallback_models_raw if isinstance(model, str)]
        if isinstance(flash_fallback_models_raw, (list, tuple))
        else []
    )

    chunking_snapshot = build_python_chunking_preprocess_snapshot_from_input(
        {
            "content_text": content_text,
            "enable_chunking": enable_chunking,
            "max_chars": effective_max_chars,
            "long_context_model": long_context_model,
        }
    )
    chunk_plan: dict[str, Any] | None = None
    if bool(chunking_snapshot.get("should_chunk")):
        candidate_plan = build_python_chunk_sentence_plan_snapshot_from_input(
            {
                "content_text": content_text,
                "lang": chosen_lang,
                "max_chars": int(chunking_snapshot.get("max_chars") or effective_max_chars),
            }
        )
        if isinstance(candidate_plan.get("chunks"), list) and candidate_plan["chunks"]:
            chunk_plan = candidate_plan

    summary_strategy = "chunked" if chunk_plan else "single_pass"
    summary_model = primary_model
    if summary_strategy == "single_pass" and len(content_text) > _MAX_SINGLE_PASS_CHARS:
        summary_model = long_context_model or primary_model

    single_pass_request_plan: dict[str, Any] | None = None
    if summary_strategy == "single_pass":
        single_pass_request_plan = build_python_llm_wrapper_plan_snapshot_from_input(
            {
                "base_model": summary_model,
                "schema_response_type": _normalize_response_type(
                    payload.get("schema_response_type")
                ),
                "json_object_response_type": _normalize_response_type(
                    payload.get("json_object_response_type")
                ),
                "max_tokens_schema": payload.get("max_tokens_schema"),
                "max_tokens_json_object": payload.get("max_tokens_json_object"),
                "base_temperature": payload.get("base_temperature"),
                "base_top_p": payload.get("base_top_p"),
                "json_temperature": payload.get("json_temperature"),
                "json_top_p": payload.get("json_top_p"),
                "fallback_models": fallback_models,
                "flash_model": payload.get("flash_model"),
                "flash_fallback_models": flash_fallback_models,
            }
        )

    return {
        "flow_kind": "url",
        "dedupe_hash": str(payload.get("dedupe_hash") or ""),
        "detected_language": detected_language,
        "chosen_lang": chosen_lang,
        "needs_ru_translation": needs_ru_translation,
        "content_length": len(content_text),
        "threshold_model": threshold_model,
        "summary_strategy": summary_strategy,
        "summary_model": summary_model,
        "effective_max_chars": int(chunking_snapshot.get("max_chars") or effective_max_chars),
        "chunk_plan": chunk_plan,
        "single_pass_request_plan": single_pass_request_plan,
    }


def build_python_forward_processing_plan(payload: dict[str, Any]) -> dict[str, Any]:
    text = str(payload.get("text") or "")
    source_label, source_title = _resolve_forward_source(payload)
    prompt = f"{source_label}: {source_title}\n\n{text}" if source_title else text
    llm_prompt, llm_prompt_truncated = _truncate_forward_prompt(prompt)
    detected_language = detect_language(text)
    chosen_lang = choose_language(
        str(payload.get("preferred_language") or "auto"), detected_language
    )
    llm_max_tokens = max(2048, min(6144, len(llm_prompt) // 4 + 2048))

    return {
        "flow_kind": "forward",
        "source_label": source_label,
        "source_title": source_title,
        "prompt": prompt,
        "llm_prompt": llm_prompt,
        "llm_prompt_truncated": llm_prompt_truncated,
        "prompt_length": len(prompt),
        "detected_language": detected_language,
        "chosen_lang": chosen_lang,
        "summary_model": _normalize_model(payload.get("primary_model")),
        "llm_max_tokens": llm_max_tokens,
    }


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_rust_processing_orchestrator_binary() -> Path | None:
    configured = os.getenv(_PROCESSING_ORCHESTRATOR_BIN_ENV)
    if configured:
        candidate = Path(configured).expanduser().resolve()
        if candidate.is_file():
            return candidate

    root = _repo_root()
    candidates = (
        root / "rust" / "target" / "release" / "bsr-processing-orchestrator",
        root / "rust" / "target" / "debug" / "bsr-processing-orchestrator",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def run_rust_processing_orchestrator_command(
    command: str,
    payload: dict[str, Any],
    *,
    timeout_ms: int = 250,
    binary_path: Path | None = None,
) -> dict[str, Any]:
    binary = binary_path or resolve_rust_processing_orchestrator_binary()
    if binary is None:
        msg = "Rust processing orchestrator binary not found"
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
            "processing orchestrator rust command failed "
            f"({command}, exit={process.returncode}): {stderr or stdout}"
        )
        raise RuntimeError(msg)

    output = (process.stdout or "").strip()
    if not output:
        msg = f"processing orchestrator rust command returned empty output ({command})"
        raise RuntimeError(msg)

    parsed = json.loads(output)
    if not isinstance(parsed, dict):
        msg = f"processing orchestrator rust command returned non-object JSON ({command})"
        raise RuntimeError(msg)
    return parsed


@dataclass(frozen=True)
class ProcessingOrchestratorRuntimeOptions:
    backend: str = "python"
    timeout_ms: int = 250


class ProcessingOrchestratorRunner:
    """Processing orchestrator runner for URL and forward execution planning."""

    def __init__(self, runtime_cfg: Any) -> None:
        self.options = ProcessingOrchestratorRuntimeOptions(
            backend=str(getattr(runtime_cfg, "migration_processing_orchestrator_backend", "python"))
            .strip()
            .lower(),
            timeout_ms=int(
                getattr(runtime_cfg, "migration_processing_orchestrator_timeout_ms", 250)
            ),
        )

    async def resolve_url_processing_plan(
        self,
        *,
        correlation_id: str | None = None,
        request_id: int | None = None,
        **payload: Any,
    ) -> dict[str, Any]:
        if self.options.backend != "rust":
            return build_python_url_processing_plan(payload)

        try:
            return await asyncio.to_thread(
                run_rust_processing_orchestrator_command,
                "url-plan",
                payload,
                timeout_ms=self.options.timeout_ms,
            )
        except Exception as exc:
            record_cutover_event(
                event_type="rust_failure",
                surface="processing_orchestrator_url",
                reason="rust_backend_failed",
                correlation_id=correlation_id,
                metadata={"backend": "rust", "request_id": request_id},
            )
            msg = (
                "Rust processing orchestrator url-plan failed; "
                "Python fallback is disabled for rust backend mode."
            )
            raise RuntimeError(msg) from exc

    async def resolve_forward_processing_plan(
        self,
        *,
        correlation_id: str | None = None,
        request_id: int | None = None,
        **payload: Any,
    ) -> dict[str, Any]:
        if self.options.backend != "rust":
            return build_python_forward_processing_plan(payload)

        try:
            return await asyncio.to_thread(
                run_rust_processing_orchestrator_command,
                "forward-plan",
                payload,
                timeout_ms=self.options.timeout_ms,
            )
        except Exception as exc:
            record_cutover_event(
                event_type="rust_failure",
                surface="processing_orchestrator_forward",
                reason="rust_backend_failed",
                correlation_id=correlation_id,
                metadata={"backend": "rust", "request_id": request_id},
            )
            msg = (
                "Rust processing orchestrator forward-plan failed; "
                "Python fallback is disabled for rust backend mode."
            )
            raise RuntimeError(msg) from exc
