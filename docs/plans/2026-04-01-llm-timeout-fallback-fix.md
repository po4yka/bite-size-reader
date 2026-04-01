# LLM Timeout Fallback Fix

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix three interconnected bugs that caused request `03feff1c2ff9` to burn 15 minutes on a single model without trying fallbacks, leave the request stuck at `pending`, and never persist the LLM call failure.

**Architecture:** The `execute_summary_workflow` loop iterates over a list of `LLMRequestConfig` objects (different models/presets). Currently, `_invoke_llm` raises `TimeoutError` which escapes the loop entirely, bypassing both fallback attempts and the `_handle_all_attempts_failed` cleanup. The fix wraps `_invoke_llm` to catch `TimeoutError`, synthesize a failed `LLMCallResult`, and let the loop continue. A safety-net status update is added to `_run_url_flow`'s exception handler.

**Tech Stack:** Python asyncio, Pydantic, unittest.mock

---

## Task 1: Catch TimeoutError in execute_summary_workflow loop

**Files:**

- Modify: `app/adapters/content/llm_response_workflow_execution.py:106-110`
- Test: `tests/test_llm_response_workflow.py`

**Step 1: Write the failing test**

Add to `tests/test_llm_response_workflow.py`:

```python
async def test_timeout_on_first_attempt_tries_next(self) -> None:
    """TimeoutError from _invoke_llm should not escape the attempt loop."""
    summary_payload = {
        "summary_250": "Summary body",
        "tldr": "TLDR text",
        "summary_1000": "Longer summary",
    }
    llm_ok = self._llm_response(summary_payload)

    # First call times out, second succeeds
    self.openrouter.chat = AsyncMock(side_effect=[TimeoutError("LLM timeout"), llm_ok])

    fallback_request = LLMRequestConfig(
        preset_name="json_object_fallback",
        messages=self.base_messages,
        response_format={"type": "json_object"},
        max_tokens=256,
        temperature=0.1,
        top_p=1.0,
        model_override="fallback-model",
    )

    with unittest.mock.patch(
        "app.adapters.content.llm_response_workflow.parse_summary_response",
        return_value=SimpleNamespace(
            shaped=summary_payload,
            errors=[],
            used_local_fix=False,
        ),
    ):
        summary = await self.workflow.execute_summary_workflow(
            message=MagicMock(),
            req_id=501,
            correlation_id="timeout-test",
            interaction_config=self.interaction,
            persistence=self.persistence,
            repair_context=self.repair_context,
            requests=[self.request, fallback_request],
            notifications=self.notifications,
        )

    assert summary is not None
    assert self.openrouter.chat.await_count == 2
    # The timed-out LLM call should still be persisted
    assert self.insert_llm_call_mock.await_count == 2
```

**Step 2: Run test to verify it fails**

Run: `cd /mnt/nvme/home/po4yka/bite-size-reader && python -m pytest tests/test_llm_response_workflow.py::LLMResponseWorkflowTests::test_timeout_on_first_attempt_tries_next -xvs`

Expected: FAIL -- `TimeoutError` escapes the loop, second attempt never reached.

**Step 3: Write the failing test for all-timeout case**

Add to `tests/test_llm_response_workflow.py`:

```python
async def test_timeout_on_all_attempts_updates_status(self) -> None:
    """When all attempts time out, _handle_all_attempts_failed must still run."""
    self.openrouter.chat = AsyncMock(side_effect=TimeoutError("LLM timeout"))

    summary = await self.workflow.execute_summary_workflow(
        message=MagicMock(),
        req_id=502,
        correlation_id="all-timeout",
        interaction_config=self.interaction,
        persistence=self.persistence,
        repair_context=self.repair_context,
        requests=[self.request],
        notifications=self.notifications,
    )

    assert summary is None
    self.update_status_mock.assert_awaited_once()
```

**Step 4: Run test to verify it fails**

Run: `cd /mnt/nvme/home/po4yka/bite-size-reader && python -m pytest tests/test_llm_response_workflow.py::LLMResponseWorkflowTests::test_timeout_on_all_attempts_updates_status -xvs`

Expected: FAIL -- `TimeoutError` escapes, `_handle_all_attempts_failed` never called, status not updated.

**Step 5: Implement the fix**

In `app/adapters/content/llm_response_workflow_execution.py`, wrap the `_invoke_llm` call at line 110 in a try/except that catches `TimeoutError` and `ConcurrencyTimeoutError`, synthesizes a failed `LLMCallResult`, and continues the loop:

```python
# Replace lines 109-110 with:
            on_retry = notifications.retry if notifications else None
            try:
                llm = await self._invoke_llm(attempt, req_id, on_retry=on_retry)
            except TimeoutError:
                logger.error(
                    "llm_invoke_timeout_skipping_attempt",
                    extra={
                        "req_id": req_id,
                        "cid": correlation_id,
                        "attempt_index": attempt_index,
                        "preset": attempt.preset_name,
                        "model": attempt.model_override,
                    },
                )
                from app.adapter_models.llm.llm_models import LLMCallResult

                llm = LLMCallResult(
                    status=CallStatus.ERROR,
                    model=attempt.model_override,
                    error_text=f"LLM call timed out for model {attempt.model_override}",
                    error_context={"message": "timeout", "timeout": True},
                )
```

This needs the `LLMCallResult` import. Add it inside the except to avoid circular imports (it's already used elsewhere in the file via `Any` typing, but this is the first concrete usage).

**Step 6: Run both tests to verify they pass**

Run: `cd /mnt/nvme/home/po4yka/bite-size-reader && python -m pytest tests/test_llm_response_workflow.py::LLMResponseWorkflowTests::test_timeout_on_first_attempt_tries_next tests/test_llm_response_workflow.py::LLMResponseWorkflowTests::test_timeout_on_all_attempts_updates_status -xvs`

Expected: PASS

**Step 7: Run full workflow test suite**

Run: `cd /mnt/nvme/home/po4yka/bite-size-reader && python -m pytest tests/test_llm_response_workflow.py -xvs`

Expected: All tests pass.

**Step 8: Commit**

```bash
git add app/adapters/content/llm_response_workflow_execution.py tests/test_llm_response_workflow.py
git commit -m "fix: catch TimeoutError in summary workflow loop to enable fallback attempts"
```

---

## Task 2: Add safety-net request status update in url_processor

**Files:**

- Modify: `app/adapters/content/url_processor.py:327-339`
- Test: `tests/test_llm_response_workflow.py` (already covers via Task 1)

**Step 1: Implement the fix**

In `app/adapters/content/url_processor.py`, add a request status update to the exception handler at line 327. The `context` variable may not exist if the exception happened during `build()`, so use a guard:

```python
# Replace lines 327-339 with:
        except Exception as exc:
            raise_if_cancelled(exc)
            logger.exception(
                "url_processing_failed",
                extra={"cid": request.correlation_id, "url": request.url_text, "error": str(exc)},
            )
            # Safety-net: ensure request is marked as failed in DB
            req_id = context.req_id if context is not None else None
            if req_id is not None:
                try:
                    from app.domain.models.request import RequestStatus

                    await self.request_repo.async_update_request_status(
                        req_id, RequestStatus.ERROR
                    )
                except Exception:
                    logger.warning(
                        "failed_to_update_request_status_on_error",
                        extra={"cid": request.correlation_id, "req_id": req_id},
                    )
            if not request.silent and not request.batch_mode:
                await self.response_formatter.send_error_notification(
                    request.message,
                    "processing_failed",
                    request.correlation_id or "unknown",
                )
            return URLProcessingFlowResult(success=False)
```

Also need to initialize `context = None` before the try block so the except can reference it safely. Check line 215-216:

```python
    async def _run_url_flow(
        self,
        request: URLFlowRequest,
    ) -> URLProcessingFlowResult:
        """Execute the URL processing pipeline (extraction -> summarization -> delivery)."""
        context: URLFlowContext | None = None
        try:
            context = await self.context_builder.build(request)
```

**Step 2: Run type check**

Run: `cd /mnt/nvme/home/po4yka/bite-size-reader && python -m mypy app/adapters/content/url_processor.py --no-error-summary 2>&1 | head -20`

Expected: No new errors.

**Step 3: Run existing url_processor tests**

Run: `cd /mnt/nvme/home/po4yka/bite-size-reader && python -m pytest tests/test_url_processor_translation.py tests/test_url_processor_batch_mode.py -xvs`

Expected: All pass.

**Step 4: Commit**

```bash
git add app/adapters/content/url_processor.py
git commit -m "fix: update request status to error in url_processor exception handler"
```

---

## Task 3: Persist timed-out LLM calls in the database

**Files:**

- Modify: `app/adapters/content/llm_response_workflow_execution.py` (already touched in Task 1)

The synthesized `LLMCallResult` from Task 1 flows naturally through the existing persistence logic at lines 115-122 (`_persist_llm_call`). No additional code needed -- the loop continuation after the except block handles this.

**Step 1: Verify with the test from Task 1**

The `test_timeout_on_first_attempt_tries_next` already asserts `insert_llm_call_mock.await_count == 2`, confirming both the timed-out and successful calls are persisted.

Run: `cd /mnt/nvme/home/po4yka/bite-size-reader && python -m pytest tests/test_llm_response_workflow.py::LLMResponseWorkflowTests::test_timeout_on_first_attempt_tries_next -xvs`

Expected: PASS (already passing from Task 1).

---

## Task 4: Full regression and lint

**Step 1: Run full test suite**

Run: `cd /mnt/nvme/home/po4yka/bite-size-reader && python -m pytest tests/test_llm_response_workflow.py tests/test_url_processor_translation.py tests/test_url_processor_batch_mode.py -v`

Expected: All pass.

**Step 2: Lint and type check**

Run: `cd /mnt/nvme/home/po4yka/bite-size-reader && make lint && make type`

Expected: Clean.

**Step 3: Format**

Run: `cd /mnt/nvme/home/po4yka/bite-size-reader && make format`

---

## Scope note

The HTTP/2 connection reuse issue (streaming fallback causing stale connections) is a separate, lower-priority concern. With the fallback loop working correctly, a timeout on one model costs 5 minutes instead of 15, and the system moves on to the next model. The HTTP/2 issue can be addressed later by either disabling HTTP/2 for non-stream fallbacks or creating a fresh httpx client after stream failures.
