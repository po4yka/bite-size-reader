from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.adapters.openrouter.openrouter_client import OpenRouterClient


class _StreamResponse:
    def __init__(self, lines: list[str], *, status_code: int = 200, payload: dict | None = None):
        self.status_code = status_code
        self.headers: dict[str, str] = {}
        self._lines = lines
        self._payload = payload or {}

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aread(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


class _StreamContext:
    def __init__(self, response: _StreamResponse):
        self._response = response

    async def __aenter__(self) -> _StreamResponse:
        return self._response

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _HttpResponse:
    def __init__(self, payload: dict[str, object], *, status_code: int = 200):
        self.status_code = status_code
        self._payload = payload
        self.headers: dict[str, str] = {}
        self._content = json.dumps(payload).encode("utf-8")

    def json(self) -> dict[str, object]:
        return self._payload


@pytest.mark.asyncio
async def test_openrouter_stream_success_invokes_delta_callback() -> None:
    from app.adapters.openrouter.openrouter_client import OpenRouterClientConfig

    client = OpenRouterClient(
        api_key="sk-or-test-key",
        model="qwen/qwen3-max",
        config=OpenRouterClientConfig(max_retries=1),
    )
    deltas: list[str] = []

    async def on_delta(delta: str) -> None:
        deltas.append(delta)

    with patch("httpx.AsyncClient") as mock_client:
        stream_lines = [
            (
                'data: {"model":"qwen/qwen3-max","choices":[{"index":0,'
                '"delta":{"content":"Hello "},"finish_reason":null}]}'
            ),
            (
                'data: {"model":"qwen/qwen3-max","choices":[{"index":0,'
                '"delta":{"content":"world"},"finish_reason":"stop"}],'
                '"usage":{"prompt_tokens":4,"completion_tokens":2}}'
            ),
            "data: [DONE]",
            "",
        ]
        stream_response = _StreamResponse(stream_lines)

        mock_client.return_value.stream.return_value = _StreamContext(stream_response)
        mock_client.return_value.post = AsyncMock()

        result = await client.chat(
            [{"role": "user", "content": "hello"}],
            stream=True,
            on_stream_delta=on_delta,
        )

    await client.aclose()

    assert result.status == "ok"
    assert result.response_text == "Hello world"
    assert "".join(deltas) == "Hello world"


@pytest.mark.asyncio
async def test_openrouter_stream_tolerates_malformed_frames() -> None:
    from app.adapters.openrouter.openrouter_client import OpenRouterClientConfig

    client = OpenRouterClient(
        api_key="sk-or-test-key",
        model="qwen/qwen3-max",
        config=OpenRouterClientConfig(max_retries=1),
    )

    with patch("httpx.AsyncClient") as mock_client:
        stream_lines = [
            "data: {this is not json}",
            (
                'data: {"model":"qwen/qwen3-max","choices":[{"index":0,'
                '"delta":{"content":"Recovered"},"finish_reason":"stop"}]}'
            ),
            "data: [DONE]",
            "",
        ]
        stream_response = _StreamResponse(stream_lines)

        mock_client.return_value.stream.return_value = _StreamContext(stream_response)
        mock_client.return_value.post = AsyncMock()

        result = await client.chat(
            [{"role": "user", "content": "hello"}],
            stream=True,
        )

    await client.aclose()

    assert result.status == "ok"
    assert result.response_text == "Recovered"


@pytest.mark.asyncio
async def test_openrouter_stream_failure_falls_back_to_non_stream() -> None:
    from app.adapters.openrouter.openrouter_client import OpenRouterClientConfig

    client = OpenRouterClient(
        api_key="sk-or-test-key",
        model="qwen/qwen3-max",
        config=OpenRouterClientConfig(max_retries=2),
    )

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.stream.side_effect = RuntimeError("stream transport failed")
        mock_client.return_value.post = AsyncMock(
            return_value=_HttpResponse(
                {
                    "model": "qwen/qwen3-max",
                    "choices": [
                        {"message": {"content": "Fallback response"}, "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 2},
                }
            )
        )

        result = await client.chat(
            [{"role": "user", "content": "hello"}],
            stream=True,
        )

    await client.aclose()

    assert result.status == "ok"
    assert result.response_text == "Fallback response"
    assert mock_client.return_value.post.await_count >= 1
