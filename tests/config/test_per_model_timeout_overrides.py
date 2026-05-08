"""Unit tests for the LLM_PER_MODEL_TIMEOUT_OVERRIDES config validator."""

from __future__ import annotations

from app.config.runtime import RuntimeConfig


def _make_runtime(**kwargs: object) -> RuntimeConfig:
    """Build a RuntimeConfig with minimal required fields plus overrides."""
    return RuntimeConfig.model_validate(kwargs)


class TestPerModelTimeoutOverridesParser:
    def test_empty_string_returns_empty_dict(self) -> None:
        cfg = _make_runtime(LLM_PER_MODEL_TIMEOUT_OVERRIDES="")
        assert cfg.llm_per_model_timeout_overrides == {}

    def test_none_returns_empty_dict(self) -> None:
        cfg = _make_runtime(LLM_PER_MODEL_TIMEOUT_OVERRIDES=None)
        assert cfg.llm_per_model_timeout_overrides == {}

    def test_single_entry(self) -> None:
        cfg = _make_runtime(LLM_PER_MODEL_TIMEOUT_OVERRIDES="moonshotai/kimi-k2.5=180")
        assert cfg.llm_per_model_timeout_overrides == {"moonshotai/kimi-k2.5": 180.0}

    def test_multiple_entries(self) -> None:
        cfg = _make_runtime(
            LLM_PER_MODEL_TIMEOUT_OVERRIDES="moonshotai/kimi-k2.5=180,minimax/minimax-m1=240"
        )
        assert cfg.llm_per_model_timeout_overrides == {
            "moonshotai/kimi-k2.5": 180.0,
            "minimax/minimax-m1": 240.0,
        }

    def test_whitespace_around_entries(self) -> None:
        cfg = _make_runtime(
            LLM_PER_MODEL_TIMEOUT_OVERRIDES=" moonshotai/kimi-k2.5 = 180 , minimax/minimax-m1 = 240 "
        )
        assert cfg.llm_per_model_timeout_overrides == {
            "moonshotai/kimi-k2.5": 180.0,
            "minimax/minimax-m1": 240.0,
        }

    def test_malformed_entry_skipped_valid_kept(self) -> None:
        cfg = _make_runtime(
            LLM_PER_MODEL_TIMEOUT_OVERRIDES="moonshotai/kimi-k2.5=180,bad-no-equals,minimax/minimax-m1=240"
        )
        assert cfg.llm_per_model_timeout_overrides == {
            "moonshotai/kimi-k2.5": 180.0,
            "minimax/minimax-m1": 240.0,
        }

    def test_non_numeric_seconds_skipped(self) -> None:
        cfg = _make_runtime(
            LLM_PER_MODEL_TIMEOUT_OVERRIDES="moonshotai/kimi-k2.5=abc,minimax/minimax-m1=240"
        )
        assert cfg.llm_per_model_timeout_overrides == {"minimax/minimax-m1": 240.0}

    def test_dict_input_passthrough(self) -> None:
        cfg = _make_runtime(
            LLM_PER_MODEL_TIMEOUT_OVERRIDES={"moonshotai/kimi-k2.5": 180, "minimax/minimax-m1": 240}
        )
        assert cfg.llm_per_model_timeout_overrides == {
            "moonshotai/kimi-k2.5": 180.0,
            "minimax/minimax-m1": 240.0,
        }

    def test_float_seconds_accepted(self) -> None:
        cfg = _make_runtime(LLM_PER_MODEL_TIMEOUT_OVERRIDES="mymodel/fast=90.5")
        assert cfg.llm_per_model_timeout_overrides == {"mymodel/fast": 90.5}

    def test_default_is_empty_dict(self) -> None:
        cfg = RuntimeConfig.model_validate({})
        assert cfg.llm_per_model_timeout_overrides == {}
