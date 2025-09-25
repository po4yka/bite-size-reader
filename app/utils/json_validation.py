from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from typing import Any

from app.core.json_utils import extract_json
from app.core.summary_contract import validate_and_shape_summary


@dataclass
class SummaryJsonParseResult:
    """Result of attempting to shape a summary JSON payload."""

    raw: dict[str, Any] | None
    shaped: dict[str, Any] | None
    used_local_fix: bool
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.shaped is not None


def parse_summary_response(
    response_json: Any,
    response_text: str | None,
) -> SummaryJsonParseResult:
    """Extract and validate a summary JSON payload from LLM outputs.

    Tries structured responses, raw text parsing, and finally local repair helpers
    before signaling failure so the caller can escalate with a repair call.
    """

    errors: list[str] = []

    candidate = _extract_structured_dict(response_json)
    if candidate is not None:
        shaped, err = _shape_candidate(candidate)
        if shaped is not None:
            return SummaryJsonParseResult(candidate, shaped, False, errors)
        errors.append(f"structured_validation_failed: {err}")

    for candidate_text, label, used_fix in _iter_text_candidates(response_text):
        parsed, parse_err = _parse_json_text(candidate_text)
        if parsed is None:
            errors.append(f"{label}_parse_failed: {parse_err}")
            continue
        shaped, val_err = _shape_candidate(parsed)
        if shaped is not None:
            return SummaryJsonParseResult(parsed, shaped, used_fix, errors)
        errors.append(f"{label}_validation_failed: {val_err}")

    # Local heuristic fallback: try robust extract_json without extra LLM calls
    try:
        extracted = extract_json(response_text or "")
    except Exception:
        extracted = None
    if isinstance(extracted, dict):
        shaped, val_err = _shape_candidate(extracted)
        if shaped is not None:
            return SummaryJsonParseResult(extracted, shaped, True, errors)
        errors.append(f"extract_json_validation_failed: {val_err}")

    repair_candidate, repair_err, _ = _attempt_local_repair(response_text)
    if repair_candidate is not None:
        shaped, val_err = _shape_candidate(repair_candidate)
        if shaped is not None:
            return SummaryJsonParseResult(repair_candidate, shaped, True, errors)
        errors.append(f"local_repair_validation_failed: {val_err}")
    elif repair_err:
        errors.append(f"local_repair_failed: {repair_err}")

    return SummaryJsonParseResult(None, None, False, errors)


def _shape_candidate(candidate: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    try:
        shaped = validate_and_shape_summary(candidate)
        finalize_summary_texts(shaped)
        return shaped, None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def finalize_summary_texts(summary: dict[str, Any]) -> None:
    for key in ("summary_250", "tldr"):
        raw = summary.get(key)
        if not isinstance(raw, str):
            continue
        cleaned = raw.strip()
        if cleaned and cleaned[-1] not in ".!?…":
            last = max(
                cleaned.rfind("."),
                cleaned.rfind("!"),
                cleaned.rfind("?"),
                cleaned.rfind("…"),
            )
            if last != -1 and last >= len(cleaned) // 3:
                cleaned = cleaned[: last + 1].rstrip()
            else:
                cleaned = cleaned.rstrip("-—")
                if cleaned and cleaned[-1] not in ".!?…":
                    cleaned = cleaned + "."
        summary[key] = cleaned


def _extract_structured_dict(response_json: Any) -> dict[str, Any] | None:
    # Handle list responses (when model returns an array instead of object)
    if isinstance(response_json, list):
        if len(response_json) > 0:
            # Try to use the first item if it's a dict
            first_item = response_json[0]
            if isinstance(first_item, dict):
                if any(
                    key in first_item
                    for key in (
                        "summary_250",
                        "tldr",
                        "summary_1000",
                        "summary250",
                        "summary1000",
                        "key_ideas",
                    )
                ):
                    return first_item
        return None

    if isinstance(response_json, dict):
        # Direct dict payload
        if any(
            key in response_json
            for key in (
                "summary_250",
                "tldr",
                "summary_1000",
                "summary250",
                "summary1000",
                "key_ideas",
            )
        ):
            return response_json
        choices = (
            response_json.get("choices") if isinstance(response_json.get("choices"), list) else []
        )
        if choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message") or {}
                parsed = message.get("parsed")
                if parsed is not None:
                    if isinstance(parsed, dict):
                        return parsed
                    try:
                        materialized = json.loads(json.dumps(parsed))
                        return materialized if isinstance(materialized, dict) else None
                    except Exception:  # noqa: BLE001
                        return None
    return None


def _iter_text_candidates(response_text: str | None) -> list[tuple[str, str, bool]]:
    if not response_text:
        return []

    base = response_text.strip()
    if not base:
        return []

    candidates: list[tuple[str, str, bool]] = []
    seen: set[str] = set()

    def add_candidate(text: str, label: str, used_fix: bool) -> None:
        normalized = text.strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        candidates.append((normalized, label, used_fix))

    add_candidate(base, "trimmed_text", False)

    without_fence = _strip_code_fence(base)
    add_candidate(without_fence, "code_fence_removed", without_fence != base)

    backtick_stripped = without_fence.strip("` ")
    add_candidate(backtick_stripped, "backtick_stripped", backtick_stripped != without_fence)

    brace_slice = _slice_between_braces(backtick_stripped or without_fence)
    if brace_slice is not None:
        add_candidate(brace_slice, "brace_slice", True)

    return candidates


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if lines and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _slice_between_braces(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


def _parse_json_text(candidate_text: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        parsed = json.loads(candidate_text)
    except json.JSONDecodeError as exc:
        return None, f"json_decode_error: {exc.msg} at line {exc.lineno} column {exc.colno}"
    except Exception as exc:  # noqa: BLE001
        return None, f"json_error: {exc}"
    if not isinstance(parsed, dict):
        return None, "parsed_value_not_object"
    return parsed, None


def _attempt_local_repair(
    response_text: str | None,
) -> tuple[dict[str, Any] | None, str | None, bool]:
    if not response_text:
        return None, None, False

    try:
        module = importlib.import_module("json_repair")
    except ModuleNotFoundError:
        return None, "json_repair_not_available", False
    except Exception as exc:  # noqa: BLE001
        return None, f"json_repair_import_error: {exc}", False

    repair_func = getattr(module, "repair_json", None)
    if not callable(repair_func):
        return None, "json_repair_missing_repair_json", False

    cleaned = _strip_code_fence(response_text.strip()).strip("` ")
    try:
        repaired_text = repair_func(cleaned)
    except Exception as exc:  # noqa: BLE001
        return None, f"json_repair_runtime_error: {exc}", False

    if not isinstance(repaired_text, str):
        return None, "json_repair_invalid_return", False

    parsed, parse_err = _parse_json_text(repaired_text.strip())
    if parsed is None:
        return None, parse_err or "json_repair_parse_failed", False
    return parsed, None, True


__all__ = ["SummaryJsonParseResult", "parse_summary_response", "finalize_summary_texts"]
