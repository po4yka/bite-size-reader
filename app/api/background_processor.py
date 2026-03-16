"""Background request processor for Mobile API with DI, Redis locks, and retries."""

from __future__ import annotations

import asyncio
import copy
import json
import random
import time
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, cast

from app.adapters.content.summarization_models import (
    EnsureSummaryPayloadRequest,
    PureSummaryRequest,
)
from app.adapters.content.url_flow_context_builder import get_url_system_prompt
from app.core.async_utils import raise_if_cancelled
from app.core.lang import choose_language, detect_language
from app.core.logging_utils import get_logger, log_exception
from app.core.url_utils import normalize_url
from app.di.database import build_runtime_database
from app.di.repositories import build_request_repository, build_summary_repository
from app.infrastructure.redis import redis_key
from app.observability.failure_observability import (
    REASON_UNKNOWN_EXTRACTION_FAILURE,
    persist_request_failure,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.adapters.content.url_processor import URLProcessor
    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager

logger = get_logger(__name__)


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int
    base_delay_ms: int
    max_delay_ms: int
    jitter_ratio: float


@dataclass
class LockHandle:
    source: str
    key: str
    token: str | None
    local_lock: asyncio.Lock | None


class StageError(Exception):
    """Wrap a failure with stage context."""

    def __init__(self, stage: str, exc: Exception):
        super().__init__(str(exc))
        self.stage = stage
        self.original = exc


class BackgroundProcessor:
    """Process background requests with idempotent locking and retries."""

    def __init__(
        self,
        *,
        cfg: AppConfig,
        db: DatabaseSessionManager,
        url_processor: URLProcessor,
        redis: Any | None,
        semaphore: asyncio.Semaphore,
        audit_func: Callable[[str, str, dict], None],
        url_processor_factory: Callable[[DatabaseSessionManager], URLProcessor] | None = None,
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.summary_repo = build_summary_repository(db)
        self.request_repo = build_request_repository(db)
        self.url_processor = url_processor
        self._url_processor_factory = url_processor_factory
        self.redis = redis
        self._sem = semaphore
        self._audit = audit_func
        self._local_locks: dict[int, asyncio.Lock] = {}
        self._lock_enabled = cfg.background.redis_lock_enabled
        self._lock_required = cfg.background.redis_lock_required
        self._lock_ttl_ms = cfg.background.lock_ttl_ms
        self._lock_skip_on_held = cfg.background.lock_skip_on_held
        self._retry = RetryPolicy(
            attempts=cfg.background.retry_attempts,
            base_delay_ms=cfg.background.retry_base_delay_ms,
            max_delay_ms=cfg.background.retry_max_delay_ms,
            jitter_ratio=cfg.background.retry_jitter_ratio,
        )

    async def process(
        self,
        request_id: int,
        *,
        correlation_id: str | None = None,
        db_path: str | None = None,
    ) -> None:
        """Process a request by id."""
        started_at = time.perf_counter()
        processor_db, processor = self._maybe_override_db(db_path)
        request: dict[str, Any] | None = None

        lock_handle = await self._acquire_lock(request_id, correlation_id)
        if lock_handle is None:
            return

        try:
            repo = self._get_request_repo_for_db(processor_db)
            request = await repo.async_get_request_by_id(request_id)
            if not request:
                logger.error(
                    "bg_request_not_found",
                    extra={"request_id": request_id, "correlation_id": correlation_id},
                )
                return

            if await self._has_existing_summary(processor_db, request_id):
                logger.info(
                    "bg_request_already_summarized",
                    extra={
                        "request_id": request_id,
                        "correlation_id": request.get("correlation_id") or correlation_id,
                    },
                )
                await self._publish_update(
                    request_id, "COMPLETED", "DONE", "Already summarized", 1.0
                )
                return

            cid = request.get("correlation_id") or correlation_id or f"bg-proc-{request_id}"
            await self._mark_status(processor_db, request_id, "processing", cid)
            await self._publish_update(
                request_id, "PROCESSING", "QUEUED", "Processing started", 0.0
            )

            logger.info(
                "bg_processing_start",
                extra={
                    "correlation_id": cid,
                    "request_id": request_id,
                    "type": request.get("type"),
                    "url": request.get("input_url"),
                },
            )

            if request.get("type") == "url":
                await self._process_url_type(request_id, request, processor_db, processor, cid)
            elif request.get("type") == "forward":
                await self._process_forward_type(request_id, request, processor_db, processor, cid)
            else:
                raise StageError(
                    "validation", ValueError(f"Unknown request type: {request.get('type')}")
                )

            await self._mark_status(processor_db, request_id, "success", cid)
            await self._publish_update(request_id, "COMPLETED", "DONE", "Processing completed", 1.0)

            logger.info(
                "bg_processing_success",
                extra={
                    "correlation_id": cid,
                    "request_id": request_id,
                    "type": request.get("type"),
                },
            )
        except StageError as exc:
            await self._handle_stage_error(
                request_id=request_id,
                correlation_id=correlation_id,
                processor_db=processor_db,
                request=request,
                stage_error=exc,
                started_at=started_at,
            )
        except asyncio.CancelledError:
            await self._handle_cancelled(
                request_id=request_id,
                correlation_id=correlation_id,
                processor_db=processor_db,
                request=request,
            )
            raise
        except Exception as exc:  # pragma: no cover - defensive
            await self._handle_unexpected_error(
                request_id=request_id,
                correlation_id=correlation_id,
                processor_db=processor_db,
                request=request,
                exc=exc,
                started_at=started_at,
            )
        finally:
            await self._release_lock(lock_handle)

    def _get_request_repo_for_db(self, db: DatabaseSessionManager) -> Any:
        if db == self.db:
            return self.request_repo
        return build_request_repository(db)

    async def _handle_stage_error(
        self,
        *,
        request_id: int,
        correlation_id: str | None,
        processor_db: DatabaseSessionManager,
        request: dict[str, Any] | None,
        stage_error: StageError,
        started_at: float,
    ) -> None:
        error_payload = self._build_error_payload(stage_error.stage, stage_error.original)
        cid = (request or {}).get("correlation_id") or correlation_id
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        target_repo = self._get_request_repo_for_db(processor_db)

        await persist_request_failure(
            request_repo=target_repo,
            logger=logger,
            request_id=request_id,
            correlation_id=cid,
            stage=stage_error.stage,
            component="background_processor",
            reason_code=error_payload["error_code"],
            error=stage_error.original,
            retryable=True,
            attempt=self._retry.attempts,
            max_attempts=self._retry.attempts,
            processing_time_ms=elapsed_ms,
        )
        if request:
            await self._mark_status(processor_db, request_id, "error", cid)
        await self._publish_update(
            request_id,
            "FAILED",
            stage_error.stage.upper(),
            str(stage_error.original),
            0.0,
            error=str(stage_error.original),
        )
        logger.error(
            "bg_processing_failed",
            exc_info=True,
            extra={"correlation_id": cid, "request_id": request_id, **error_payload},
        )

    async def _handle_cancelled(
        self,
        *,
        request_id: int,
        correlation_id: str | None,
        processor_db: DatabaseSessionManager,
        request: dict[str, Any] | None,
    ) -> None:
        logger.warning(
            "bg_processing_cancelled",
            extra={"correlation_id": correlation_id, "request_id": request_id},
        )
        if request:
            await self._mark_status(
                processor_db,
                request_id,
                "cancelled",
                correlation_id or request.get("correlation_id"),
            )
        await self._publish_update(request_id, "CANCELLED", "CANCELLED", "Task cancelled", 0.0)

    async def _handle_unexpected_error(
        self,
        *,
        request_id: int,
        correlation_id: str | None,
        processor_db: DatabaseSessionManager,
        request: dict[str, Any] | None,
        exc: Exception,
        started_at: float,
    ) -> None:
        error_payload = self._build_error_payload("unknown", exc)
        cid = (request or {}).get("correlation_id") or correlation_id
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        target_repo = self._get_request_repo_for_db(processor_db)

        await persist_request_failure(
            request_repo=target_repo,
            logger=logger,
            request_id=request_id,
            correlation_id=cid,
            stage="unknown",
            component="background_processor",
            reason_code=REASON_UNKNOWN_EXTRACTION_FAILURE,
            error=exc,
            retryable=True,
            attempt=self._retry.attempts,
            max_attempts=self._retry.attempts,
            processing_time_ms=elapsed_ms,
        )
        if request:
            await self._mark_status(processor_db, request_id, "error", cid)
        await self._publish_update(request_id, "FAILED", "UNKNOWN", str(exc), 0.0, error=str(exc))
        logger.error(
            "bg_processing_failed",
            exc_info=True,
            extra={"correlation_id": cid, "request_id": request_id, **error_payload},
        )

    def _maybe_override_db(
        self, db_path: str | None
    ) -> tuple[DatabaseSessionManager, URLProcessor]:
        if not db_path:
            return self.db, self.url_processor

        if self._url_processor_factory is None:
            msg = "BackgroundProcessor requires url_processor_factory for DB overrides"
            raise RuntimeError(msg)

        try:
            override_cfg = replace(self.cfg, runtime=replace(self.cfg.runtime, db_path=db_path))
        except TypeError:
            override_cfg = copy.copy(self.cfg)
            override_runtime = copy.copy(self.cfg.runtime)
            cast("Any", override_runtime).db_path = db_path
            cast("Any", override_cfg).runtime = override_runtime
        override_db = build_runtime_database(override_cfg)
        override_processor = self._url_processor_factory(override_db)

        return override_db, override_processor

    async def _acquire_lock(self, request_id: int, correlation_id: str | None) -> LockHandle | None:
        if self._lock_enabled and self.redis:
            key = redis_key(self.cfg.redis.prefix, "bg", "req", str(request_id))
            token = f"worker-{time.time_ns()}"
            try:
                acquired = await self.redis.set(key, token, nx=True, px=self._lock_ttl_ms)
            except Exception as exc:
                logger.warning(
                    "bg_lock_redis_error",
                    exc_info=True,
                    extra={
                        "correlation_id": correlation_id,
                        "request_id": request_id,
                        "error": str(exc),
                    },
                )
                if self._lock_required:
                    raise StageError("lock", exc) from exc
                acquired = False

            if acquired:
                logger.info(
                    "bg_lock_acquired",
                    extra={
                        "correlation_id": correlation_id,
                        "request_id": request_id,
                        "source": "redis",
                        "ttl_ms": self._lock_ttl_ms,
                    },
                )
                return LockHandle("redis", key, token, None)

            if self._lock_skip_on_held:
                logger.info(
                    "bg_lock_held_skip",
                    extra={
                        "correlation_id": correlation_id,
                        "request_id": request_id,
                        "source": "redis",
                    },
                )
                return None

        lock = self._local_locks.setdefault(request_id, asyncio.Lock())
        if lock.locked() and self._lock_skip_on_held:
            logger.info(
                "bg_lock_held_skip",
                extra={
                    "correlation_id": correlation_id,
                    "request_id": request_id,
                    "source": "local",
                },
            )
            return None

        await lock.acquire()
        logger.info(
            "bg_lock_acquired",
            extra={
                "correlation_id": correlation_id,
                "request_id": request_id,
                "source": "local",
                "ttl_ms": self._lock_ttl_ms,
            },
        )
        return LockHandle("local", str(request_id), None, lock)

    async def _release_lock(self, handle: LockHandle) -> None:
        if not handle:
            return

        if handle.source == "redis" and self.redis:
            script = """
            if redis.call('get', KEYS[1]) == ARGV[1] then
                return redis.call('del', KEYS[1])
            else
                return 0
            end
            """
            try:
                await self.redis.eval(script, 1, handle.key, handle.token)
            except Exception:  # pragma: no cover - best effort
                logger.warning(
                    "bg_lock_release_failed",
                    exc_info=True,
                    extra={"key": handle.key, "source": "redis"},
                )
        elif handle.source == "local" and handle.local_lock and handle.local_lock.locked():
            handle.local_lock.release()

        # Clean up local lock entry to prevent memory leak
        if handle.source == "local":
            request_id = int(handle.key)
            lock_obj = self._local_locks.get(request_id)
            if lock_obj is not None and not lock_obj.locked():
                self._local_locks.pop(request_id, None)

    async def _process_url_type(
        self,
        request_id: int,
        request: dict[str, Any],
        db: DatabaseSessionManager,
        url_processor: URLProcessor,
        correlation_id: str,
    ) -> None:
        normalized_url = normalize_url(request.get("input_url") or "")

        await self._publish_update(
            request_id, "PROCESSING", "EXTRACTION", "Extracting content...", 0.2
        )
        content_text, _content_source, metadata = await self._run_stage(
            "extraction",
            correlation_id,
            lambda: url_processor.content_extractor.extract_content_pure(
                url=normalized_url,
                correlation_id=correlation_id,
                request_id=request_id,
            ),
        )

        if not content_text or not content_text.strip():
            raise StageError(
                "extraction", ValueError("Content extraction failed - no content returned")
            )

        lang = self._resolve_request_language(request, content_text, metadata=metadata)
        system_prompt = get_url_system_prompt(lang)

        await self._publish_update(
            request_id, "PROCESSING", "SUMMARIZATION", "Summarizing content...", 0.5
        )
        summary_json = await self._run_stage(
            "summarization",
            correlation_id,
            lambda: url_processor.pure_summary_service.summarize(
                PureSummaryRequest(
                    content_text=content_text,
                    chosen_lang=lang,
                    system_prompt=system_prompt,
                    correlation_id=correlation_id,
                )
            ),
        )

        if not summary_json:
            raise StageError(
                "summarization", ValueError("Summary generation failed - no summary returned")
            )

        await self._publish_update(
            request_id, "PROCESSING", "VALIDATION", "Validating summary...", 0.8
        )
        summary_json = await self._run_stage(
            "validation",
            correlation_id,
            lambda: url_processor.pure_summary_service.ensure_summary_payload(
                EnsureSummaryPayloadRequest(
                    summary=summary_json,
                    req_id=request_id,
                    content_text=content_text,
                    chosen_lang=lang,
                    correlation_id=correlation_id,
                )
            ),
        )

        await self._publish_update(request_id, "PROCESSING", "SAVING", "Saving summary...", 0.9)
        repo = self.summary_repo if db == self.db else build_summary_repository(db)
        await repo.async_upsert_summary(
            request_id=request_id,
            lang=lang,
            json_payload=summary_json,
            is_read=False,
        )

    def _resolve_request_language(
        self,
        request: dict[str, Any],
        content_text: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Resolve output language, treating stored 'auto' as unresolved.

        Prefers extractor-provided language hints (for example YouTube transcript
        language) when available, then falls back to text detection.
        """
        preferred = str(request.get("lang_detected") or "").strip().lower()
        if preferred in {"en", "ru"}:
            return preferred
        metadata_lang = ""
        if isinstance(metadata, dict):
            metadata_lang = str(metadata.get("detected_lang") or "").strip().lower()
        if metadata_lang in {"en", "ru"}:
            return choose_language(self.cfg.runtime.preferred_lang, metadata_lang)
        detected = detect_language(content_text)
        return choose_language(self.cfg.runtime.preferred_lang, detected)

    async def _process_forward_type(
        self,
        request_id: int,
        request: dict[str, Any],
        db: DatabaseSessionManager,
        url_processor: URLProcessor,
        correlation_id: str,
    ) -> None:
        lang = request.get("lang_detected") or "auto"
        if lang == "auto":
            content_text = request.get("content_text") or ""
            detected = detect_language(content_text)
            lang = choose_language(self.cfg.runtime.preferred_lang, detected)
        system_prompt = get_url_system_prompt(lang)

        await self._publish_update(
            request_id, "PROCESSING", "SUMMARIZATION", "Summarizing content...", 0.5
        )
        summary_json = await self._run_stage(
            "summarization",
            correlation_id,
            lambda: url_processor.pure_summary_service.summarize(
                PureSummaryRequest(
                    content_text=request.get("content_text") or "",
                    chosen_lang=lang,
                    system_prompt=system_prompt,
                    correlation_id=correlation_id,
                )
            ),
        )

        if not summary_json:
            raise StageError(
                "summarization", ValueError("Summary generation failed - no summary returned")
            )

        await self._publish_update(request_id, "PROCESSING", "SAVING", "Saving summary...", 0.9)
        repo = self.summary_repo if db == self.db else build_summary_repository(db)
        await repo.async_upsert_summary(
            request_id=request_id,
            lang=lang,
            json_payload=summary_json,
            is_read=False,
        )

    async def _run_stage(
        self,
        stage: str,
        correlation_id: str,
        func: Callable[[], Awaitable[Any]],
    ) -> Any:
        try:
            return await self._run_with_backoff(func, stage, correlation_id)
        except Exception as exc:
            raise StageError(stage, exc) from exc

    async def _run_with_backoff(
        self,
        func: Callable[[], Awaitable[Any]],
        stage: str,
        correlation_id: str,
    ) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, self._retry.attempts + 1):
            try:
                return await func()
            except Exception as exc:
                raise_if_cancelled(exc)
                last_error = exc
                delay_ms = min(
                    self._retry.max_delay_ms,
                    int(self._retry.base_delay_ms * (2 ** (attempt - 1))),
                )
                jitter = int(delay_ms * self._retry.jitter_ratio)
                delay_ms = max(0, delay_ms + random.randint(-jitter, jitter))

                if attempt >= self._retry.attempts:
                    break

                logger.warning(
                    "bg_retry",
                    extra={
                        "correlation_id": correlation_id,
                        "stage": stage,
                        "attempt": attempt,
                        "delay_ms": delay_ms,
                        "error": str(exc),
                    },
                )
                await asyncio.sleep(delay_ms / 1000)

        if last_error:
            raise last_error
        raise RuntimeError("Retry loop exited without result or error")

    async def _has_existing_summary(self, db: DatabaseSessionManager, request_id: int) -> bool:
        repo = self.summary_repo if db == self.db else build_summary_repository(db)
        try:
            return bool(await repo.async_get_summary_by_request(request_id))
        except Exception as exc:
            logger.debug(
                "bg_summary_check_failed",
                extra={
                    "request_id": request_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            return False

    async def _mark_status(
        self, db: DatabaseSessionManager, request_id: int, status: str, correlation_id: str | None
    ) -> None:
        repo = self.request_repo if db == self.db else build_request_repository(db)
        try:
            await repo.async_update_request_status_with_correlation(
                request_id, status, correlation_id
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "bg_request_status_save_failed",
                exc_info=True,
                extra={"request_id": request_id, "status": status, "error": str(exc)},
            )

    async def _publish_update(
        self,
        request_id: int,
        status: str,
        stage: str,
        message: str,
        progress: float,
        error: str | None = None,
    ) -> None:
        """Publish status update to Redis Pub/Sub."""
        if not self.redis:
            return

        payload = {
            "request_id": request_id,
            "status": status,
            "stage": stage,
            "message": message,
            "progress": progress,
            "error": error,
            "timestamp": time.time(),
        }
        channel = f"processing:request:{request_id}"
        try:
            await self.redis.publish(channel, json.dumps(payload))
        except Exception as exc:
            logger.warning(
                "bg_redis_publish_failed",
                exc_info=True,
                extra={"channel": channel, "error": str(exc)},
            )

    @staticmethod
    def _build_error_payload(stage: str, exc: Exception) -> dict[str, Any]:
        code_map = {
            "extraction": "EXTRACTION_FAILED",
            "summarization": "LLM_FAILED",
            "validation": "VALIDATION_FAILED",
            "lock": "LOCK_FAILED",
        }
        return {
            "error_type": exc.__class__.__name__,
            "error_code": code_map.get(stage, "UNKNOWN_ERROR"),
            "error_message": str(exc),
            "error_stage": stage,
        }


_default_processor: BackgroundProcessor | None = None
_default_lock = asyncio.Lock()


async def _get_default_processor() -> BackgroundProcessor:
    global _default_processor
    if _default_processor:
        return _default_processor

    async with _default_lock:
        if _default_processor:
            return _default_processor
        from app.di.api import get_current_api_runtime

        _default_processor = get_current_api_runtime().background_processor
        return _default_processor


async def process_url_request(
    request_id: int, db_path: str | None = None, correlation_id: str | None = None
) -> None:
    processor = await _get_default_processor()
    task = asyncio.create_task(
        processor.process(request_id, correlation_id=correlation_id, db_path=db_path)
    )
    # Background processing tasks - store reference if needed or use fire-and-forget safely
    if not hasattr(processor, "_processing_tasks"):
        processor._processing_tasks = set()  # type: ignore[attr-defined]
    tasks = processor._processing_tasks  # type: ignore[attr-defined]
    tasks.add(task)

    def _on_task_done(t: asyncio.Task) -> None:
        tasks.discard(t)
        if t.cancelled():
            return
        exc = t.exception()
        if exc:
            log_exception(
                logger,
                "bg_processing_task_failed",
                exc,
                request_id=request_id,
                correlation_id=correlation_id,
            )

    task.add_done_callback(_on_task_done)
