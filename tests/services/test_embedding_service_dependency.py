"""Regression tests: embedding backend dependency failures must be quiet.

On hosts where ``torch``/CUDA shared libraries are missing, importing
``sentence_transformers`` raises on *every* call. The service must surface a
single typed :class:`EmbeddingDependencyUnavailableError`, cache it so the
expensive failing import is not retried per summary, and let callers degrade
without dumping a traceback for each row.
"""

from __future__ import annotations

import builtins

import pytest

from app.application.ports.search import EmbeddingDependencyUnavailableError
from app.infrastructure.embedding.embedding_service import EmbeddingService


def test_ensure_model_raises_typed_error_and_caches_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = {"count": 0}
    real_import = builtins.__import__

    def _failing_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "sentence_transformers":
            attempts["count"] += 1
            raise OSError("libcudart.so.13: cannot open shared object file")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", _failing_import)

    service = EmbeddingService()

    with pytest.raises(EmbeddingDependencyUnavailableError):
        service._ensure_model("paraphrase-multilingual-MiniLM-L12-v2")

    # Second call must short-circuit on the cached failure -- no repeat import.
    with pytest.raises(EmbeddingDependencyUnavailableError):
        service._ensure_model("paraphrase-multilingual-MiniLM-L12-v2")

    assert attempts["count"] == 1


@pytest.mark.asyncio
async def test_generate_embedding_propagates_dependency_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = builtins.__import__

    def _failing_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "sentence_transformers":
            raise OSError("libcudart.so.13: cannot open shared object file")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", _failing_import)

    service = EmbeddingService()
    with pytest.raises(EmbeddingDependencyUnavailableError):
        await service.generate_embedding("some text", language="en")
