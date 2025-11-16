import os
import unittest

import pytest


class TestModelValidation(unittest.TestCase):
    def test_validate_model_name_allows_openrouter_ids(self) -> None:
        from app.config import validate_model_name

        valid_models = [
            "openai/gpt-4o-mini",
            "openai/gpt-5",
            "google/gemini-2.5-pro",
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
        from app.config import load_config

        old_env = os.environ.copy()
        try:
            os.environ.clear()
            os.environ["API_ID"] = "123456"
            os.environ["API_HASH"] = "a" * 32
            os.environ["BOT_TOKEN"] = "123456:abcdefghijklmnopqrstuvwxyz0123456789abcdefghij"
            os.environ["FIRECRAWL_API_KEY"] = "fc_" + "b" * 20
            os.environ["OPENROUTER_API_KEY"] = "or_" + "c" * 20
            os.environ["ALLOWED_USER_IDS"] = "123456789"
            os.environ["OPENROUTER_MODEL"] = "openai/gpt-5"
            os.environ["OPENROUTER_FALLBACK_MODELS"] = (
                "fallback/model,google/gemini-2.5-pro, invalid|name"
            )

            cfg = load_config()

            assert cfg.openrouter.model == "openai/gpt-5"
            assert cfg.openrouter.fallback_models == ("fallback/model", "google/gemini-2.5-pro")
        finally:
            os.environ.clear()
            os.environ.update(old_env)

    def test_load_config_respects_env_overrides(self) -> None:
        from app.config import load_config

        old_env = os.environ.copy()
        try:
            os.environ.clear()
            os.environ["API_ID"] = "123456"
            os.environ["API_HASH"] = "a" * 32
            os.environ["BOT_TOKEN"] = "123456:abcdefghijklmnopqrstuvwxyz0123456789abcdefghij"
            os.environ["FIRECRAWL_API_KEY"] = "fc_" + "f" * 20
            os.environ["OPENROUTER_API_KEY"] = "or_" + "g" * 20
            os.environ["ALLOWED_USER_IDS"] = "1001, 1002"
            os.environ["OPENROUTER_MAX_TOKENS"] = "4096"
            os.environ["OPENROUTER_TOP_P"] = "0.75"
            os.environ["LOG_LEVEL"] = "debug"
            os.environ["DEBUG_PAYLOADS"] = "true"

            cfg = load_config()

            assert cfg.openrouter.max_tokens == 4096
            self.assertAlmostEqual(cfg.openrouter.top_p or 0, 0.75)
            assert cfg.runtime.log_level == "DEBUG"
            assert cfg.runtime.debug_payloads
            assert cfg.telegram.allowed_user_ids == (1001, 1002)
        finally:
            os.environ.clear()
            os.environ.update(old_env)

    def test_load_config_defaults_apply_when_optional_missing(self) -> None:
        from app.config import load_config

        old_env = os.environ.copy()
        try:
            os.environ.clear()
            os.environ["API_ID"] = "123456"
            os.environ["API_HASH"] = "a" * 32
            os.environ["BOT_TOKEN"] = "123456:abcdefghijklmnopqrstuvwxyz0123456789abcdefghij"
            os.environ["FIRECRAWL_API_KEY"] = "fc_" + "h" * 20
            os.environ["OPENROUTER_API_KEY"] = "or_" + "i" * 20
            os.environ["ALLOWED_USER_IDS"] = "77"

            cfg = load_config()

            assert cfg.runtime.db_path == "/data/app.db"
            assert cfg.openrouter.temperature == 0.2
            # New defaults include fallback models
            assert cfg.openrouter.fallback_models == (
                "deepseek/deepseek-r1:free",
                "qwen/qwen3-max",
                "openai/gpt-4o",
            )
            # New default primary model
            assert cfg.openrouter.model == "deepseek/deepseek-v3-0324:free"
            # New default long context model
            assert cfg.openrouter.long_context_model == "moonshotai/kimi-k2:free"
        finally:
            os.environ.clear()
            os.environ.update(old_env)

    def test_load_config_allows_stub_credentials(self) -> None:
        from app.config import load_config

        old_env = os.environ.copy()
        try:
            os.environ.clear()
            os.environ["FIRECRAWL_API_KEY"] = "fc_" + "j" * 20
            os.environ["OPENROUTER_API_KEY"] = "or_" + "k" * 20

            cfg = load_config(allow_stub_telegram=True)

            assert cfg.telegram.api_id == 1
            assert cfg.telegram.api_hash.startswith("test_api_hash_placeholder_value")
            assert cfg.telegram.bot_token.startswith("1000000000:")
            assert cfg.telegram.allowed_user_ids == ()
        finally:
            os.environ.clear()
            os.environ.update(old_env)

    def test_load_config_requires_allowed_users_when_not_stub(self) -> None:
        from app.config import load_config

        old_env = os.environ.copy()
        try:
            os.environ.clear()
            os.environ["API_ID"] = "123456"
            os.environ["API_HASH"] = "a" * 32
            os.environ["BOT_TOKEN"] = "123456:abcdefghijklmnopqrstuvwxyz0123456789abcdefghij"
            os.environ["FIRECRAWL_API_KEY"] = "fc_" + "l" * 20
            os.environ["OPENROUTER_API_KEY"] = "or_" + "m" * 20

            with pytest.raises(RuntimeError):
                load_config()
        finally:
            os.environ.clear()
            os.environ.update(old_env)


if __name__ == "__main__":
    unittest.main()
