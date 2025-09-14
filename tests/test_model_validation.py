import os
import unittest


class TestModelValidation(unittest.TestCase):
    def test_validate_model_name_allows_openrouter_ids(self):
        from app.config import _validate_model_name

        valid_models = [
            "openai/gpt-4o-mini",
            "openai/gpt-5",
            "anthropic/claude-3.5-sonnet:beta",
            "meta-llama/llama-3.1-8b-instruct:free",
            "google/gemini-1.5-pro-exp-0827",
            "nousresearch/hermes-3-llama-3.1-405b:free",
        ]

        for m in valid_models:
            self.assertEqual(_validate_model_name(m), m)

    def test_validate_model_name_rejects_invalid(self):
        from app.config import _validate_model_name

        invalid_models = [
            "evil..model",
            "name<",
            "name>",
            "bad\\name",
            "white space",
            "semi;colon",
        ]

        for m in invalid_models:
            with self.assertRaises(ValueError):
                _validate_model_name(m)

    def test_load_config_with_openrouter_model_and_fallbacks(self):
        from app.config import load_config

        # Save current env and set required variables
        old_env = os.environ.copy()
        try:
            os.environ["API_ID"] = "123456"
            os.environ["API_HASH"] = "a" * 32
            os.environ["BOT_TOKEN"] = "123456:abcdefghijklmnopqrstuvwxyz0123456789abcdefghij"
            os.environ["FIRECRAWL_API_KEY"] = "fc_" + "b" * 20
            os.environ["OPENROUTER_API_KEY"] = "or_" + "c" * 20
            os.environ["OPENROUTER_MODEL"] = "openai/gpt-5"
            os.environ["OPENROUTER_FALLBACK_MODELS"] = (
                "fallback/model,anthropic/claude-3.5-sonnet:beta, invalid|name"
            )

            cfg = load_config()

            self.assertEqual(cfg.openrouter.model, "openai/gpt-5")
            # Invalid fallback (with "|") should be skipped
            self.assertEqual(
                cfg.openrouter.fallback_models,
                ("fallback/model", "anthropic/claude-3.5-sonnet:beta"),
            )
        finally:
            os.environ.clear()
            os.environ.update(old_env)


if __name__ == "__main__":
    unittest.main()
