import os
import unittest
from unittest.mock import patch

import pytest


class TestModelValidation(unittest.TestCase):
    def test_validate_model_name_allows_openrouter_ids(self) -> None:
        from app.config import validate_model_name

        valid_models = [
            "deepseek/deepseek-v3.2",
            "qwen/qwen3-max",
            "moonshotai/kimi-k2.5",
        ]

        for model in valid_models:
            assert validate_model_name(model) == model

    def test_validate_model_name_rejects_invalid(self) -> None:
        from app.config import validate_model_name

        invalid_models = [
            "evil..model",
            "name<",
            "name>",
            "bad\\name",
            "white space",
            "semi;colon",
        ]

        for model in invalid_models:
            with pytest.raises(ValueError):
                validate_model_name(model)

    def test_load_config_with_openrouter_model_and_fallbacks(self) -> None:
        from app.config import Settings

        # Use Settings directly with _env_file=None to prevent .env file loading
        test_env = {
            "API_ID": "123456",
            "API_HASH": "a" * 32,
            "BOT_TOKEN": "123456:abcdefghijklmnopqrstuvwxyz0123456789abcdefghij",
            "FIRECRAWL_API_KEY": "fc_" + "b" * 20,
            "OPENROUTER_API_KEY": "or_" + "c" * 20,
            "ALLOWED_USER_IDS": "123456789",
            "OPENROUTER_MODEL": "qwen/qwen3-max",
            # fallback/model is valid (no invalid chars), invalid|name has pipe which is invalid
            "OPENROUTER_FALLBACK_MODELS": "fallback/model,google/gemini-2.5-pro, invalid|name",
        }

        with patch.dict(os.environ, test_env, clear=True):
            settings = Settings(_env_file=None)
            cfg = settings.as_app_config()

            # fallback/model is a valid model name (alphanumeric + slash)
            # invalid|name is filtered out (pipe is not in allowed chars)
            assert cfg.openrouter.fallback_models == ("fallback/model", "google/gemini-2.5-pro")

    def test_load_config_respects_env_overrides(self) -> None:
        from app.config import Settings

        test_env = {
            "API_ID": "123456",
            "API_HASH": "a" * 32,
            "BOT_TOKEN": "123456:abcdefghijklmnopqrstuvwxyz0123456789abcdefghij",
            "FIRECRAWL_API_KEY": "fc_" + "f" * 20,
            "OPENROUTER_API_KEY": "or_" + "g" * 20,
            "ALLOWED_USER_IDS": "1001, 1002",
            "OPENROUTER_MAX_TOKENS": "4096",
            "OPENROUTER_TOP_P": "0.75",
            "LOG_LEVEL": "debug",
            "DEBUG_PAYLOADS": "true",
        }

        with patch.dict(os.environ, test_env, clear=True):
            settings = Settings(_env_file=None)
            cfg = settings.as_app_config()

            assert cfg.openrouter.max_tokens == 4096
            self.assertAlmostEqual(cfg.openrouter.top_p or 0, 0.75)
            assert cfg.runtime.log_level == "DEBUG"
            assert cfg.runtime.debug_payloads
            assert cfg.telegram.allowed_user_ids == (1001, 1002)

    def test_load_config_defaults_apply_when_optional_missing(self) -> None:
        from app.config import Settings

        test_env = {
            "API_ID": "123456",
            "API_HASH": "a" * 32,
            "BOT_TOKEN": "123456:abcdefghijklmnopqrstuvwxyz0123456789abcdefghij",
            "FIRECRAWL_API_KEY": "fc_" + "h" * 20,
            "OPENROUTER_API_KEY": "or_" + "i" * 20,
            "ALLOWED_USER_IDS": "77",
        }

        with patch.dict(os.environ, test_env, clear=True):
            settings = Settings(_env_file=None)
            cfg = settings.as_app_config()

            # Check that defaults are applied when env vars are not set
            assert cfg.runtime.db_path == "/data/app.db"
            assert cfg.openrouter.temperature == 0.2
            # DeepSeek v3.2 is most reliable for structured outputs
            assert cfg.openrouter.model == "deepseek/deepseek-v3.2"
            # Default fallback models from config.py
            assert cfg.openrouter.fallback_models == (
                "moonshotai/kimi-k2.5",
                "qwen/qwen3-max",
                "deepseek/deepseek-r1",
            )

    def test_load_config_allows_stub_credentials(self) -> None:
        from app.config import Settings

        test_env = {
            "FIRECRAWL_API_KEY": "fc_" + "j" * 20,
            "OPENROUTER_API_KEY": "or_" + "k" * 20,
        }

        with patch.dict(os.environ, test_env, clear=True):
            # Provide stub telegram credentials directly
            # _env_file and telegram dict are pydantic-settings internals
            settings = Settings(
                _env_file=None,
                allow_stub_telegram=True,
                telegram={
                    "api_id": 1,
                    "api_hash": "test_api_hash_placeholder_value___",
                    "bot_token": "1000000000:TESTTOKENPLACEHOLDER1234567890ABC",
                    "allowed_user_ids": (),
                },
            )
            cfg = settings.as_app_config()

            assert cfg.telegram.api_id == 1
            assert cfg.telegram.api_hash.startswith("test_api_hash_placeholder_value")
            assert cfg.telegram.bot_token.startswith("1000000000:")
            assert cfg.telegram.allowed_user_ids == ()

    def test_load_config_requires_allowed_users_when_not_stub(self) -> None:
        from app.config import Settings

        test_env = {
            "API_ID": "123456",
            "API_HASH": "a" * 32,
            "BOT_TOKEN": "123456:abcdefghijklmnopqrstuvwxyz0123456789abcdefghij",
            "FIRECRAWL_API_KEY": "fc_" + "l" * 20,
            "OPENROUTER_API_KEY": "or_" + "m" * 20,
            # No ALLOWED_USER_IDS
        }

        with patch.dict(os.environ, test_env, clear=True):
            with pytest.raises(RuntimeError):
                Settings(_env_file=None)


if __name__ == "__main__":
    unittest.main()
