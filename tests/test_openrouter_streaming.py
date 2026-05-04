from __future__ import annotations

import httpx
import pytest

from app.adapters.openrouter.openrouter_client import OpenRouterClient, OpenRouterClientConfig

OR_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"


@pytest.mark.asyncio
async def test_openrouter_stream_success_invokes_delta_callback(respx_mock) -> None:
    client = OpenRouterClient(
        api_key="sk-or-test-key",
        model="qwen/qwen3-max",
        config=OpenRouterClientConfig(max_retries=1),
    )
    deltas: list[str] = []

    async def on_delta(delta: str) -> None:
        deltas.append(delta)

    sse_body = (
        b'data: {"model":"qwen/qwen3-max","choices":[{"index":0,'
        b'"delta":{"content":"Hello "},"finish_reason":null}]}\n'
        b'data: {"model":"qwen/qwen3-max","choices":[{"index":0,'
        b'"delta":{"content":"world"},"finish_reason":"stop"}],'
        b'"usage":{"prompt_tokens":4,"completion_tokens":2}}\n'
        b"data: [DONE]\n"
        b"\n"
    )
    respx_mock.post(OR_CHAT_URL).mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=sse_body,
        )
    )

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
async def test_openrouter_stream_tolerates_malformed_frames(respx_mock) -> None:
    client = OpenRouterClient(
        api_key="sk-or-test-key",
        model="qwen/qwen3-max",
        config=OpenRouterClientConfig(max_retries=1),
    )

    sse_body = (
        b"data: {this is not json}\n"
        b'data: {"model":"qwen/qwen3-max","choices":[{"index":0,'
        b'"delta":{"content":"Recovered"},"finish_reason":"stop"}]}\n'
        b"data: [DONE]\n"
        b"\n"
    )
    respx_mock.post(OR_CHAT_URL).mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=sse_body,
        )
    )

    result = await client.chat(
        [{"role": "user", "content": "hello"}],
        stream=True,
    )
    await client.aclose()

    assert result.status == "ok"
    assert result.response_text == "Recovered"


@pytest.mark.asyncio
async def test_openrouter_stream_failure_falls_back_to_non_stream(respx_mock) -> None:
    client = OpenRouterClient(
        api_key="sk-or-test-key",
        model="qwen/qwen3-max",
        config=OpenRouterClientConfig(max_retries=2),
    )

    fallback_json = {
        "model": "qwen/qwen3-max",
        "choices": [{"message": {"content": "Fallback response"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 4, "completion_tokens": 2},
    }
    # First call: raise a transport-level error so streaming fails
    # Second call: non-stream fallback succeeds
    respx_mock.post(OR_CHAT_URL).mock(
        side_effect=[
            httpx.ConnectError("stream transport failed"),
            httpx.Response(200, json=fallback_json),
        ]
    )

    result = await client.chat(
        [{"role": "user", "content": "hello"}],
        stream=True,
    )
    await client.aclose()

    assert result.status == "ok"
    assert result.response_text == "Fallback response"
    assert respx_mock.calls.call_count >= 1
