"""Synchronous embedding bridge for CocoIndex @coco.fn workers.

CocoIndex calls transform functions synchronously from Rust worker threads.
This module spins up a dedicated daemon asyncio loop so we can reuse the
existing async embedding implementations (sentence-transformers, Gemini)
without re-implementing provider switching.

The singleton embedding service and event loop are initialised lazily on
first call and shared across all CocoIndex worker threads.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from typing import Any

_UUID_NAMESPACE = uuid.NAMESPACE_OID

_lock = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None
_loop_thread: threading.Thread | None = None
_service: Any | None = None


def _ensure_runtime() -> None:
    global _loop, _loop_thread, _service
    with _lock:
        if _service is not None:
            return
        from app.config import load_config
        from app.infrastructure.embedding.embedding_factory import create_embedding_service

        cfg = load_config(allow_stub_telegram=True)
        _service = create_embedding_service(cfg.embedding)
        _loop = asyncio.new_event_loop()
        _loop_thread = threading.Thread(
            target=_loop.run_forever,
            daemon=True,
            name="coco-embed-loop",
        )
        _loop_thread.start()


def embed_text_sync(text: str, language: str | None = None) -> list[float]:
    """Generate an embedding vector synchronously via the shared async service.

    Intended to be called from CocoIndex @coco.fn decorated transforms.
    Thread-safe; initialises the daemon loop on first call.
    """
    _ensure_runtime()
    assert _loop is not None and _service is not None  # guaranteed by _ensure_runtime
    fut = asyncio.run_coroutine_threadsafe(
        _service.generate_embedding(text, language=language, task_type="document"),
        _loop,
    )
    embedding = fut.result(timeout=60.0)
    return embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)


def summary_id_to_point_id(request_id: int, summary_id: int) -> str:
    """Compute the Qdrant point UUID that matches QdrantVectorStore._str_to_uuid.

    Key format must exactly match: f"{request_id}:{summary_id}"
    Namespace must exactly match: uuid.NAMESPACE_OID
    """
    return str(uuid.uuid5(_UUID_NAMESPACE, f"{request_id}:{summary_id}"))
