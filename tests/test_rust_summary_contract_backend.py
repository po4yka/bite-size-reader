from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.core.summary_contract_impl.rust_backend import validate_with_backend


def _python_fallback(payload: dict[str, object]) -> dict[str, object]:
    return {"backend": "python", "payload": payload}


def test_python_backend_default_uses_python_fallback(monkeypatch) -> None:
    monkeypatch.delenv("SUMMARY_CONTRACT_BACKEND", raising=False)

    with patch(
        "app.core.summary_contract_impl.rust_backend.run_rust_validate_and_shape_summary"
    ) as rust_call:
        result = validate_with_backend({"summary_250": "x"}, python_fallback=_python_fallback)

    assert result["backend"] == "python"
    rust_call.assert_not_called()


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
