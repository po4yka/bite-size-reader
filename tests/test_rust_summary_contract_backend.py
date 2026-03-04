from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.core.summary_contract_impl.rust_backend import validate_with_backend


def _python_fallback(payload: dict[str, object]) -> dict[str, object]:
    return {"backend": "python", "payload": payload}


def test_default_backend_prefers_rust_when_binary_available(monkeypatch) -> None:
    monkeypatch.delenv("SUMMARY_CONTRACT_BACKEND", raising=False)

    with (
        patch(
            "app.core.summary_contract_impl.rust_backend.resolve_rust_binary",
            return_value=Path("/tmp/bsr-summary-contract"),
        ),
        patch(
            "app.core.summary_contract_impl.rust_backend.run_rust_validate_and_shape_summary",
            return_value={"backend": "rust"},
        ) as rust_call,
    ):
        result = validate_with_backend({"summary_250": "x"}, python_fallback=_python_fallback)

    assert result["backend"] == "rust"
    rust_call.assert_called_once()


def test_default_backend_falls_back_to_python_when_binary_missing(monkeypatch) -> None:
    monkeypatch.delenv("SUMMARY_CONTRACT_BACKEND", raising=False)

    with (
        patch(
            "app.core.summary_contract_impl.rust_backend.resolve_rust_binary",
            return_value=None,
        ),
        patch("app.core.summary_contract_impl.rust_backend.record_cutover_event") as event_call,
    ):
        result = validate_with_backend({"summary_250": "x"}, python_fallback=_python_fallback)

    assert result["backend"] == "python"
    event_call.assert_called_once()
    assert event_call.call_args.kwargs["event_type"] == "python_fallback"
    assert event_call.call_args.kwargs["surface"] == "summary_contract"


def test_auto_backend_uses_rust_when_binary_is_available(monkeypatch) -> None:
    monkeypatch.setenv("SUMMARY_CONTRACT_BACKEND", "auto")

    with (
        patch(
            "app.core.summary_contract_impl.rust_backend.resolve_rust_binary",
            return_value=Path("/tmp/bsr-summary-contract"),
        ),
        patch(
            "app.core.summary_contract_impl.rust_backend.run_rust_validate_and_shape_summary",
            return_value={"backend": "rust"},
        ) as rust_call,
    ):
        result = validate_with_backend({"summary_250": "x"}, python_fallback=_python_fallback)

    assert result == {"backend": "rust"}
    rust_call.assert_called_once()


def test_rust_backend_falls_back_when_rust_execution_fails(monkeypatch) -> None:
    monkeypatch.setenv("SUMMARY_CONTRACT_BACKEND", "rust")

    with (
        patch(
            "app.core.summary_contract_impl.rust_backend.resolve_rust_binary",
            return_value=Path("/tmp/bsr-summary-contract"),
        ),
        patch(
            "app.core.summary_contract_impl.rust_backend.run_rust_validate_and_shape_summary",
            side_effect=RuntimeError("boom"),
        ),
    ):
        result = validate_with_backend({"summary_250": "x"}, python_fallback=_python_fallback)

    assert result["backend"] == "python"


def test_python_backend_forces_python_path(monkeypatch) -> None:
    monkeypatch.setenv("SUMMARY_CONTRACT_BACKEND", "python")

    with patch(
        "app.core.summary_contract_impl.rust_backend.run_rust_validate_and_shape_summary"
    ) as rust_call:
        result = validate_with_backend({"summary_250": "x"}, python_fallback=_python_fallback)

    assert result["backend"] == "python"
    rust_call.assert_not_called()
