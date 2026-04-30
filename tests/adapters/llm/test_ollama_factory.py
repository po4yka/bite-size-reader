from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from app.adapters.llm.factory import LLMClientFactory


def test_factory_creates_openai_compatible_cloud_ollama_client() -> None:
    config = SimpleNamespace(
        ollama=SimpleNamespace(
            base_url="https://ollama.example.com/v1",
            api_key="ollama-cloud-key",
            model="llama3.3",
            fallback_models=("qwen2.5",),
            enable_structured_outputs=False,
            max_response_size_mb=25,
        ),
        runtime=SimpleNamespace(
            request_timeout_sec=45,
            debug_payloads=False,
        ),
    )

    client = cast("Any", LLMClientFactory.create("ollama", config))  # type: ignore[arg-type]

    assert client.provider_name == "ollama"
    assert client._base_url == "https://ollama.example.com/v1"
    assert client._model == "llama3.3"
    assert client._fallback_models == ["qwen2.5"]
    assert client._enable_structured_outputs is False
