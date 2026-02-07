from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

logger = logging.getLogger(__name__)

TFn = TypeVar("TFn", bound=Callable[..., Any])

if TYPE_CHECKING:
    from fastapi import APIRouter, Depends
else:
    try:
        from fastapi import APIRouter, Depends
    except Exception:  # pragma: no cover - fallback for environments without compatible FastAPI
        logger.debug("fastapi_import_failed", exc_info=True)

        class APIRouter:
            def __init__(self, *_: Any, **__: Any) -> None:
                return None

            def include_router(self, *_: Any, **__: Any) -> None:
                return None

            def _decorator(self, *_: Any, **__: Any) -> Callable[[TFn], TFn]:
                def decorator(fn: TFn) -> TFn:
                    return fn

                return decorator

            def post(self, *_: Any, **__: Any) -> Callable[[TFn], TFn]:
                return self._decorator()

            def get(self, *_: Any, **__: Any) -> Callable[[TFn], TFn]:
                return self._decorator()

            def delete(self, *_: Any, **__: Any) -> Callable[[TFn], TFn]:
                return self._decorator()

        def _fallback_depends(*_: Any, **__: Any) -> Any:
            return None

        Depends: Any = _fallback_depends
