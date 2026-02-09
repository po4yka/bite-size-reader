"""gRPC client library for ProcessingService.

Provides both async and synchronous clients for submitting URLs
and receiving streaming status updates.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

import grpc
from grpc import StatusCode

from app.protos import (
    processing_pb2 as _processing_pb2,
    processing_pb2_grpc as _processing_pb2_grpc,
)

if TYPE_CHECKING:
    from types import TracebackType

    from app.protos import processing_pb2, processing_pb2_grpc
else:
    # Cast to Any to silence mypy errors with generated code
    processing_pb2: Any = _processing_pb2
    processing_pb2_grpc: Any = _processing_pb2_grpc

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessingResult:
    """Result of a URL processing operation.

    Attributes:
        request_id: Unique identifier for the request
        status: Final status (COMPLETED, FAILED, etc.)
        stage: Final processing stage
        summary_id: ID of the generated summary (if successful)
        error: Error message (if failed)
        duration_seconds: Total processing time
    """

    request_id: int
    status: str
    stage: str
    summary_id: int | None = None
    error: str | None = None
    duration_seconds: float = 0.0

    @property
    def is_success(self) -> bool:
        """Check if processing completed successfully."""
        return self.status == "COMPLETED" and self.error is None


@dataclass(frozen=True)
class ProcessingUpdate:
    """Individual status update during processing.

    Attributes:
        request_id: Unique identifier for the request
        status: Current processing status
        stage: Current processing stage
        message: Human-readable status message
        progress: Progress percentage (0.0 to 1.0)
        summary_id: ID of the generated summary (when completed)
        error: Error details (when failed)
    """

    request_id: int
    status: str
    stage: str
    message: str
    progress: float
    summary_id: int | None = None
    error: str | None = None


class ProcessingClientError(Exception):
    """Base exception for ProcessingClient errors."""


class ConnectionError(ProcessingClientError):
    """Raised when unable to connect to the gRPC server."""


class ProcessingFailedError(ProcessingClientError):
    """Raised when URL processing fails."""

    def __init__(self, message: str, result: ProcessingResult):
        super().__init__(message)
        self.result = result


class TimeoutError(ProcessingClientError):
    """Raised when processing exceeds the timeout."""


class ValidationError(ProcessingClientError):
    """Raised when the request is invalid."""


class ProcessingClient:
    """Async gRPC client for the ProcessingService.

    This client provides a high-level interface for submitting URLs
    and receiving streaming status updates.

    Example:
        ```python
        async with ProcessingClient("localhost:50051") as client:
            # Process URL and get final result
            result = await client.process_url("https://example.com")
            if result.is_success:
                print(f"Summary ID: {result.summary_id}")

            # Or stream updates for real-time progress
            async for update in client.submit_url("https://example.com"):
                print(f"Progress: {update.progress:.0%} - {update.message}")
        ```
    """

    def __init__(
        self,
        target: str = "localhost:50051",
        *,
        timeout: float = 300.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        credentials: grpc.ChannelCredentials | None = None,
        options: list[tuple[str, Any]] | None = None,
    ):
        """Initialize the ProcessingClient.

        Args:
            target: gRPC server address (e.g., "localhost:50051")
            timeout: Maximum time to wait for processing (seconds)
            max_retries: Maximum number of connection retries
            retry_delay: Initial delay between retries (seconds)
            credentials: Optional channel credentials for TLS
            options: Additional gRPC channel options
        """
        self.target = target
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.credentials = credentials
        self.options = options or [
            ("grpc.keepalive_time_ms", 10000),
            ("grpc.keepalive_timeout_ms", 5000),
            ("grpc.http2.max_pings_without_data", 0),
            ("grpc.http2.min_time_between_pings_ms", 10000),
        ]

        self._channel: grpc.aio.Channel | None = None
        self._stub: processing_pb2_grpc.ProcessingServiceStub | None = None
        self._connected = False

    async def connect(self) -> None:
        """Establish connection to the gRPC server.

        Raises:
            ConnectionError: If unable to connect after retries
        """
        if self._connected:
            return

        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                if self.credentials:
                    self._channel = grpc.aio.secure_channel(
                        self.target, self.credentials, options=self.options
                    )
                else:
                    self._channel = grpc.aio.insecure_channel(self.target, options=self.options)

                # Wait for channel to be ready
                await asyncio.wait_for(
                    self._channel.channel_ready(),
                    timeout=5.0,
                )

                self._stub = processing_pb2_grpc.ProcessingServiceStub(self._channel)
                self._connected = True

                logger.debug("grpc_client_connected", extra={"target": self.target})
                return

            except TimeoutError as e:
                last_error = e
                logger.warning(
                    "grpc_connection_timeout",
                    extra={"target": self.target, "attempt": attempt + 1},
                )
            except grpc.RpcError as e:
                last_error = e
                logger.warning(
                    "grpc_connection_failed",
                    extra={
                        "target": self.target,
                        "attempt": attempt + 1,
                        "code": e.code(),
                    },
                )

            # Close failed channel
            if self._channel:
                await self._channel.close()
                self._channel = None

            # Exponential backoff
            if attempt < self.max_retries - 1:
                delay = self.retry_delay * (2**attempt)
                await asyncio.sleep(delay)

        raise ConnectionError(
            f"Failed to connect to {self.target} after {self.max_retries} attempts"
        ) from last_error

    async def close(self) -> None:
        """Close the gRPC connection."""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None
            self._connected = False
            logger.debug("grpc_client_closed")

    async def __aenter__(self) -> ProcessingClient:
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit."""
        await self.close()

    async def _ensure_connected(self) -> None:
        """Ensure client is connected before operations."""
        if not self._connected:
            await self.connect()

    def _map_status(self, status_code: int) -> str:
        """Map protobuf status code to string."""
        return processing_pb2.ProcessingStatus.Name(status_code).replace(  # type: ignore[attr-defined]
            "ProcessingStatus_", ""
        )

    def _map_stage(self, stage_code: int) -> str:
        """Map protobuf stage code to string."""
        return processing_pb2.ProcessingStage.Name(stage_code).replace(  # type: ignore[attr-defined]
            "ProcessingStage_", ""
        )

    async def submit_url(
        self,
        url: str,
        *,
        language: str = "auto",
        force_refresh: bool = False,
    ) -> AsyncIterator[ProcessingUpdate]:
        """Submit a URL for processing and stream status updates.

        This is a low-level method that yields each status update as it
        arrives from the server. For most use cases, use `process_url()`
        instead to get the final result.

        Args:
            url: The URL to process
            language: Preferred language (e.g., "en", "ru", "auto")
            force_refresh: If True, re-process even if cached

        Yields:
            ProcessingUpdate objects containing status information

        Raises:
            ConnectionError: If not connected to server
            ValidationError: If URL is invalid
            ProcessingFailedError: If processing fails
        """
        await self._ensure_connected()
        assert self._stub is not None

        request = processing_pb2.SubmitUrlRequest(  # type: ignore[attr-defined]
            url=url,
            language=language,
            force_refresh=force_refresh,
        )

        try:
            async for update in self._stub.SubmitUrl(request, timeout=self.timeout):
                yield ProcessingUpdate(
                    request_id=update.request_id,
                    status=self._map_status(update.status),
                    stage=self._map_stage(update.stage),
                    message=update.message,
                    progress=update.progress,
                    summary_id=update.summary_id if update.summary_id else None,
                    error=update.error if update.error else None,
                )
        except grpc.RpcError as e:
            self._handle_rpc_error(e, url)

    def _handle_rpc_error(self, error: grpc.RpcError, url: str) -> None:
        """Convert gRPC errors to appropriate exceptions."""
        code = error.code()
        details = error.details() or "Unknown error"

        if code == StatusCode.INVALID_ARGUMENT:
            raise ValidationError(f"Invalid URL '{url}': {details}") from error
        if code == StatusCode.DEADLINE_EXCEEDED:
            raise TimeoutError(f"Processing timed out for '{url}': {details}") from error
        if code == StatusCode.UNAVAILABLE:
            raise ConnectionError(f"Server unavailable: {details}") from error
        raise ProcessingClientError(f"RPC error ({code}): {details}") from error

    async def process_url(
        self,
        url: str,
        *,
        language: str = "auto",
        force_refresh: bool = False,
        progress_callback: Callable[[ProcessingUpdate], None] | None = None,
    ) -> ProcessingResult:
        """Process a URL and return the final result.

        This is the high-level method for URL processing. It submits the URL,
        waits for completion, and returns the final result.

        Args:
            url: The URL to process
            language: Preferred language (e.g., "en", "ru", "auto")
            force_refresh: If True, re-process even if cached
            progress_callback: Optional callback for progress updates

        Returns:
            ProcessingResult containing the final status and summary ID

        Raises:
            ConnectionError: If not connected to server
            ValidationError: If URL is invalid
            ProcessingFailedError: If processing fails
            TimeoutError: If processing exceeds timeout
        """
        start_time = asyncio.get_event_loop().time()
        last_update: ProcessingUpdate | None = None

        async for update in self.submit_url(url, language=language, force_refresh=force_refresh):
            last_update = update

            if progress_callback:
                try:
                    progress_callback(update)
                except Exception:
                    logger.warning("progress_callback_failed", exc_info=True)

        if last_update is None:
            raise ProcessingClientError("No updates received from server")

        duration = asyncio.get_event_loop().time() - start_time

        result = ProcessingResult(
            request_id=last_update.request_id,
            status=last_update.status,
            stage=last_update.stage,
            summary_id=last_update.summary_id,
            error=last_update.error,
            duration_seconds=duration,
        )

        if not result.is_success:
            raise ProcessingFailedError(
                f"Processing failed for '{url}': {result.error}",
                result=result,
            )

        return result

    async def process_urls(
        self,
        urls: list[str],
        *,
        language: str = "auto",
        force_refresh: bool = False,
        max_concurrent: int = 5,
        progress_callback: Callable[[str, ProcessingUpdate], None] | None = None,
    ) -> list[ProcessingResult]:
        """Process multiple URLs concurrently.

        Args:
            urls: List of URLs to process
            language: Preferred language for all URLs
            force_refresh: If True, re-process even if cached
            max_concurrent: Maximum number of concurrent requests
            progress_callback: Optional callback(url, update) for progress

        Returns:
            List of ProcessingResult objects (one per URL)

        Note:
            Failed processing results are included in the list with
            error information, rather than raising exceptions.
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        results: list[ProcessingResult | Exception] = []

        async def process_one(url: str) -> ProcessingResult | Exception:
            async with semaphore:
                try:
                    # Capture progress_callback in local variable to satisfy type checker
                    cb = progress_callback
                    if cb:
                        return await self.process_url(
                            url,
                            language=language,
                            force_refresh=force_refresh,
                            progress_callback=lambda u: cb(url, u),
                        )
                    return await self.process_url(
                        url,
                        language=language,
                        force_refresh=force_refresh,
                        progress_callback=None,
                    )
                except Exception as e:
                    return e

        tasks = [asyncio.create_task(process_one(url)) for url in urls]
        results = await asyncio.gather(*tasks)

        # Convert exceptions to failed results
        final_results: list[ProcessingResult] = []
        for _url, result in zip(urls, results, strict=False):
            if isinstance(result, Exception):
                final_results.append(
                    ProcessingResult(
                        request_id=-1,
                        status="FAILED",
                        stage="UNSPECIFIED",
                        error=str(result),
                    )
                )
            else:
                final_results.append(result)

        return final_results


@asynccontextmanager
async def processing_client(
    target: str = "localhost:50051",
    **kwargs: Any,
) -> AsyncIterator[ProcessingClient]:
    """Context manager for creating and managing a ProcessingClient.

    Example:
        ```python
        async with processing_client("localhost:50051") as client:
            result = await client.process_url("https://example.com")
        ```
    """
    client = ProcessingClient(target, **kwargs)
    try:
        await client.connect()
        yield client
    finally:
        await client.close()


class SyncProcessingClient:
    """Synchronous wrapper for ProcessingClient.

    Provides a blocking interface for environments where async is not suitable.

    Example:
        ```python
        with SyncProcessingClient("localhost:50051") as client:
            result = client.process_url("https://example.com")
            print(f"Summary ID: {result.summary_id}")
        ```
    """

    def __init__(
        self,
        target: str = "localhost:50051",
        **kwargs: Any,
    ):
        """Initialize the synchronous client.

        Args:
            target: gRPC server address
            **kwargs: Additional arguments passed to ProcessingClient
        """
        self._async_client = ProcessingClient(target, **kwargs)
        self._loop: asyncio.AbstractEventLoop | None = None

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create an event loop."""
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop

    def _run_async(self, coro: Any) -> Any:
        """Run an async coroutine synchronously."""
        loop = self._get_loop()
        return loop.run_until_complete(coro)

    def connect(self) -> None:
        """Connect to the server."""
        self._run_async(self._async_client.connect())

    def close(self) -> None:
        """Close the connection."""
        self._run_async(self._async_client.close())
        if self._loop and not self._loop.is_running():
            self._loop.close()

    def __enter__(self) -> SyncProcessingClient:
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Context manager exit."""
        self.close()

    def process_url(
        self,
        url: str,
        *,
        language: str = "auto",
        force_refresh: bool = False,
    ) -> ProcessingResult:
        """Process a URL synchronously.

        Args:
            url: The URL to process
            language: Preferred language
            force_refresh: If True, re-process even if cached

        Returns:
            ProcessingResult with final status
        """
        return self._run_async(
            self._async_client.process_url(
                url,
                language=language,
                force_refresh=force_refresh,
            )
        )

    def process_urls(
        self,
        urls: list[str],
        *,
        language: str = "auto",
        force_refresh: bool = False,
        max_concurrent: int = 5,
    ) -> list[ProcessingResult]:
        """Process multiple URLs synchronously.

        Args:
            urls: List of URLs to process
            language: Preferred language
            force_refresh: If True, re-process even if cached
            max_concurrent: Maximum concurrent requests

        Returns:
            List of ProcessingResult objects
        """
        return self._run_async(
            self._async_client.process_urls(
                urls,
                language=language,
                force_refresh=force_refresh,
                max_concurrent=max_concurrent,
            )
        )
