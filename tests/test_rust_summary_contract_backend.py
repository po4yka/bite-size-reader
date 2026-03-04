from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.summary_contract_impl.rust_backend import validate_with_backend


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
        result = validate_with_backend({"summary_250": "x"})

    assert result["backend"] == "rust"
    rust_call.assert_called_once()


def test_missing_binary_raises_without_python_fallback(monkeypatch) -> None:
    monkeypatch.delenv("SUMMARY_CONTRACT_BACKEND", raising=False)

    with (
        patch(
            "app.core.summary_contract_impl.rust_backend.resolve_rust_binary",
            return_value=None,
        ),
        patch("app.core.summary_contract_impl.rust_backend.record_cutover_event") as event_call,
    ):
        with pytest.raises(FileNotFoundError):
            validate_with_backend({"summary_250": "x"})

    event_call.assert_called_once()
    assert event_call.call_args.kwargs["event_type"] == "rust_failure"
    assert event_call.call_args.kwargs["surface"] == "summary_contract"


def test_legacy_auto_backend_is_ignored_and_rust_is_used(monkeypatch) -> None:
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
        result = validate_with_backend({"summary_250": "x"})

    assert result == {"backend": "rust"}
    rust_call.assert_called_once()


def test_rust_backend_failure_raises_without_python_fallback(monkeypatch) -> None:
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
        patch("app.core.summary_contract_impl.rust_backend.record_cutover_event") as event_call,
    ):
        with pytest.raises(RuntimeError, match="boom"):
            validate_with_backend({"summary_250": "x"})

    event_call.assert_called_once()
    assert event_call.call_args.kwargs["event_type"] == "rust_failure"


def test_legacy_python_backend_is_ignored_and_rust_is_used(monkeypatch) -> None:
    monkeypatch.setenv("SUMMARY_CONTRACT_BACKEND", "python")

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
        result = validate_with_backend({"summary_250": "x"})

    assert result["backend"] == "rust"
    rust_call.assert_called_once()
