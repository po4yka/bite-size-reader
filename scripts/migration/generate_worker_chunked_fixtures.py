"""Generate/check chunked worker finalization fixtures from Python baselines."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

INPUT_DIR = Path("docs/migration/fixtures/worker_chunked/input")
EXPECTED_DIR = Path("docs/migration/fixtures/worker_chunked/expected")


def _load_migration_dependencies() -> tuple[Any, Any]:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from app.core.summary_aggregate import aggregate_chunk_summaries
    from app.core.summary_contract import validate_and_shape_summary

    return aggregate_chunk_summaries, validate_and_shape_summary


def _canonicalize(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    if isinstance(value, dict):
        return {key: _canonicalize(item) for key, item in value.items()}
    return value


def _build_attempt_output(payload: dict[str, Any]) -> dict[str, Any]:
    error_text = str(payload.get("error_text") or "").strip() or None
    return {
        "preset_name": payload.get("preset_name"),
        "model_override": None,
        "llm_result": {
            "status": "error" if error_text else "ok",
            "model": "fixture-model",
            "response_text": None,
            "response_json": None,
            "openrouter_response_text": None,
            "openrouter_response_json": None,
            "tokens_prompt": None,
            "tokens_completion": None,
            "cost_usd": None,
            "latency_ms": None,
            "error_text": error_text,
            "request_headers": None,
            "request_messages": None,
            "endpoint": "/api/v1/chat/completions",
            "structured_output_used": True,
            "structured_output_mode": "json_object",
            "error_context": None
            if error_text is None
            else {
                "status_code": None,
                "message": error_text,
                "api_error": error_text,
                "request_id": None,
                "surface": "chunked_url",
            },
        },
    }


def _shape_summary(summary_payload: Any) -> dict[str, Any] | None:
    _, validate_and_shape_summary = _load_migration_dependencies()
    if not isinstance(summary_payload, dict):
        return None
    return validate_and_shape_summary(summary_payload)


def _build_expected(payload: dict[str, Any]) -> dict[str, Any]:
    if str(payload.get("type") or "").strip() != "chunked_url_finalization":
        msg = f"unsupported fixture type: {payload.get('type')}"
        raise ValueError(msg)

    fixture_payload = payload.get("payload")
    if not isinstance(fixture_payload, dict):
        msg = "fixture payload must be a JSON object"
        raise ValueError(msg)

    chunk_attempts_raw = fixture_payload.get("chunk_attempts")
    if not isinstance(chunk_attempts_raw, list):
        msg = "chunk_attempts must be a JSON array"
        raise ValueError(msg)

    synthesis_attempt_raw = fixture_payload.get("synthesis_attempt")
    synthesis_attempt = synthesis_attempt_raw if isinstance(synthesis_attempt_raw, dict) else None

    attempts = [
        _build_attempt_output(item) for item in chunk_attempts_raw if isinstance(item, dict)
    ]
    chunk_summaries = [
        shaped
        for item in chunk_attempts_raw
        if isinstance(item, dict)
        for shaped in [_shape_summary(item.get("summary"))]
        if shaped is not None
    ]
    chunk_success_count = len(chunk_summaries)

    if synthesis_attempt is not None:
        attempts.append(_build_attempt_output(synthesis_attempt))

    if chunk_success_count == 0:
        all_attempts = [
            *(item for item in chunk_attempts_raw if isinstance(item, dict)),
            *([synthesis_attempt] if synthesis_attempt is not None else []),
        ]
        last_error = next(
            (
                str(item.get("error_text") or "").strip()
                for item in reversed(all_attempts)
                if str(item.get("error_text") or "").strip()
            ),
            "all_chunk_attempts_failed",
        )
        return {
            "status": "error",
            "summary": None,
            "attempts": attempts,
            "terminal_attempt_index": len(attempts) - 1 if attempts else None,
            "error_text": last_error,
            "chunk_success_count": 0,
            "used_synthesis": False,
        }

    aggregate_chunk_summaries, validate_and_shape_summary = _load_migration_dependencies()
    aggregate_summary = validate_and_shape_summary(aggregate_chunk_summaries(chunk_summaries))
    synthesis_summary = _shape_summary(
        synthesis_attempt.get("summary") if synthesis_attempt is not None else None
    )
    used_synthesis = synthesis_summary is not None
    terminal_attempt_index = (
        len(attempts) - 1
        if used_synthesis
        else next(
            (
                index
                for index in range(len(chunk_attempts_raw) - 1, -1, -1)
                if _shape_summary(
                    chunk_attempts_raw[index].get("summary")
                    if isinstance(chunk_attempts_raw[index], dict)
                    else None
                )
                is not None
            ),
            None,
        )
    )

    return {
        "status": "ok",
        "summary": synthesis_summary or aggregate_summary,
        "attempts": attempts,
        "terminal_attempt_index": terminal_attempt_index,
        "error_text": None,
        "chunk_success_count": chunk_success_count,
        "used_synthesis": used_synthesis,
    }


def _process_fixture(input_path: Path, *, check: bool) -> bool:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        print(f"fixture must be a JSON object: {input_path}")
        return False

    expected = _canonicalize(_build_expected(payload))
    output_path = EXPECTED_DIR / f"{input_path.stem}.json"

    if check:
        if not output_path.exists():
            print(f"missing expected fixture: {output_path}")
            return False
        current = _canonicalize(json.loads(output_path.read_text(encoding="utf-8")))
        if current != expected:
            print(f"stale expected fixture: {output_path}")
            return False
        return True

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(expected, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {output_path}")
    return True


def main() -> int:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from app.migration.fixture_runner import parse_check_flag, run_fixture_cli

    check = parse_check_flag(__doc__)
    return run_fixture_cli(
        input_dir=INPUT_DIR,
        process_fixture=_process_fixture,
        check=check,
    )


if __name__ == "__main__":
    raise SystemExit(main())
