from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.content.content_chunker import ContentChunker


class _DummySemaphore:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


def _make_chunker(*, llm_provider: str = "openrouter") -> ContentChunker:
    cfg = cast(
        "Any",
        SimpleNamespace(
            runtime=SimpleNamespace(
                llm_provider=llm_provider,
                max_concurrent_calls=3,
                migration_worker_backend="python",
            ),
            openrouter=SimpleNamespace(
                temperature=0.2,
                top_p=0.9,
                max_tokens=None,
                model="primary-model",
                structured_output_mode="json_object",
            ),
        ),
    )
    return ContentChunker(
        cfg=cfg,
        openrouter=MagicMock(),
        response_formatter=MagicMock(),
        audit_func=MagicMock(),
        sem=lambda: _DummySemaphore(),
    )


@pytest.mark.asyncio
async def test_process_chunks_uses_rust_worker_when_enabled() -> None:
    chunker = _make_chunker()
    chunker.worker_runner = MagicMock()
    chunker.worker_runner.enabled = True
    chunker.worker_runner.execute_chunked_url = AsyncMock(
        return_value={
            "status": "ok",
            "summary": {
                "summary_250": "Worker summary",
                "summary_1000": "Worker detailed summary",
                "tldr": "Worker TLDR",
            },
            "attempts": [],
            "chunk_success_count": 2,
            "used_synthesis": True,
        }
    )

    result = await chunker.process_chunks(
        chunks=["alpha beta gamma", "delta epsilon zeta"],
        system_prompt="system prompt",
        chosen_lang="en",
        req_id=7,
        correlation_id="cid",
    )

    assert result == {
        "summary_250": "Worker summary",
        "summary_1000": "Worker detailed summary",
        "tldr": "Worker TLDR",
    }
    cast("Any", chunker.openrouter.chat).assert_not_called()
    chunker.worker_runner.execute_chunked_url.assert_awaited_once()
    kwargs = chunker.worker_runner.execute_chunked_url.await_args.kwargs
    chunk_requests = kwargs["chunk_requests"]
    assert len(chunk_requests) == 2
    assert chunk_requests[0].preset_name == "chunk_1"
    assert chunk_requests[1].preset_name == "chunk_2"
    assert chunk_requests[0].model_override == "primary-model"
    assert kwargs["synthesis_request"].preset_name == "chunk_synthesis"
    assert kwargs["max_concurrent_calls"] == 3


@pytest.mark.asyncio
async def test_process_chunks_uses_python_path_when_rust_worker_disabled() -> None:
    chunker = _make_chunker()
    chunker.worker_runner = MagicMock()
    chunker.worker_runner.enabled = False
    chunker.worker_runner.execute_chunked_url = AsyncMock()
    cast("Any", chunker.openrouter).chat = AsyncMock(
        side_effect=[
            SimpleNamespace(
                status="ok",
                response_json={
                    "choices": [
                        {
                            "message": {
                                "parsed": {
                                    "summary_250": "Chunk one summary.",
                                    "summary_1000": "Chunk one longer summary.",
                                    "tldr": "Chunk one TLDR.",
                                }
                            }
                        }
                    ]
                },
                response_text=None,
                error_text=None,
            ),
            SimpleNamespace(
                status="ok",
                response_json={
                    "choices": [
                        {
                            "message": {
                                "parsed": {
                                    "summary_250": "Chunk two summary.",
                                    "summary_1000": "Chunk two longer summary.",
                                    "tldr": "Chunk two TLDR.",
                                }
                            }
                        }
                    ]
                },
                response_text=None,
                error_text=None,
            ),
            SimpleNamespace(
                status="ok",
                response_json={
                    "choices": [
                        {
                            "message": {
                                "parsed": {
                                    "summary_250": "Synthesized summary.",
                                    "summary_1000": "Synthesized longer summary.",
                                    "tldr": "Synthesized TLDR.",
                                }
                            }
                        }
                    ]
                },
                response_text=None,
                error_text=None,
            ),
        ]
    )

    result = await chunker.process_chunks(
        chunks=["alpha beta gamma", "delta epsilon zeta"],
        system_prompt="system prompt",
        chosen_lang="en",
        req_id=8,
        correlation_id="cid",
    )

    assert result is not None
    assert result["summary_250"] == "Synthesized summary."
    assert cast("Any", chunker.openrouter.chat).await_count == 3
    chunker.worker_runner.execute_chunked_url.assert_not_called()
