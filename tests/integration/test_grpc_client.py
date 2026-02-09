"""Integration tests for the gRPC client library.

These tests use mocked gRPC stubs to test the client logic without
requiring a running gRPC server.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import grpc
import pytest

from app.grpc import (
    ConnectionError,
    ProcessingClient,
    ProcessingClientError,
    ProcessingFailedError,
    ProcessingResult,
    ProcessingUpdate,
    SyncProcessingClient,
    TimeoutError,
    ValidationError,
    processing_client,
)
from app.protos import processing_pb2


@pytest.fixture
def mock_channel():
    """Create a mock gRPC channel."""
    channel = MagicMock()
    channel.channel_ready = AsyncMock()
    channel.close = AsyncMock()
    return channel


@pytest.fixture
def mock_stub():
    """Create a mock gRPC stub with streaming response."""
    return MagicMock()


class TestProcessingClientConnection:
    """Test client connection management."""

    @pytest.mark.asyncio
    async def test_connect_success(self, mock_channel, mock_stub):
        """Test successful connection to server."""
        with patch("grpc.aio.insecure_channel", return_value=mock_channel):
            with patch(
                "app.grpc.client.processing_pb2_grpc.ProcessingServiceStub",
                return_value=mock_stub,
            ):
                client = ProcessingClient("localhost:50051")
                await client.connect()

                assert client._connected
                assert client._stub is not None
                mock_channel.channel_ready.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_retry_on_failure(self, mock_channel):
        """Test connection retry logic."""
        mock_channel.channel_ready.side_effect = [
            TimeoutError(),
            TimeoutError(),
            None,  # Success on third attempt
        ]

        with patch("grpc.aio.insecure_channel", return_value=mock_channel):
            with patch("asyncio.sleep", AsyncMock()):  # Skip actual delays
                client = ProcessingClient("localhost:50051", max_retries=3, retry_delay=0.1)
                await client.connect()

                assert client._connected
                assert mock_channel.channel_ready.call_count == 3

    @pytest.mark.asyncio
    async def test_connect_failure_after_max_retries(self, mock_channel):
        """Test connection failure after exhausting retries."""
        mock_channel.channel_ready.side_effect = TimeoutError()

        with patch("grpc.aio.insecure_channel", return_value=mock_channel):
            with patch("asyncio.sleep", AsyncMock()):
                client = ProcessingClient("localhost:50051", max_retries=2, retry_delay=0.01)

                with pytest.raises(ConnectionError) as exc_info:
                    await client.connect()

                assert "Failed to connect" in str(exc_info.value)
                assert mock_channel.channel_ready.call_count == 2

    @pytest.mark.asyncio
    async def test_connect_with_grpc_error(self, mock_channel):
        """Test connection handling of gRPC errors."""
        rpc_error = grpc.RpcError()
        rpc_error.code = MagicMock(return_value=grpc.StatusCode.UNAVAILABLE)
        mock_channel.channel_ready.side_effect = rpc_error

        with patch("grpc.aio.insecure_channel", return_value=mock_channel):
            with patch("asyncio.sleep", AsyncMock()):
                client = ProcessingClient("localhost:50051", max_retries=1, retry_delay=0.01)

                with pytest.raises(ConnectionError):
                    await client.connect()

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_channel, mock_stub):
        """Test async context manager."""
        with patch("grpc.aio.insecure_channel", return_value=mock_channel):
            with patch(
                "app.grpc.client.processing_pb2_grpc.ProcessingServiceStub",
                return_value=mock_stub,
            ):
                async with ProcessingClient("localhost:50051") as client:
                    assert client._connected

                # After exiting context, should be closed
                assert not client._connected
                mock_channel.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_idempotent(self, mock_channel, mock_stub):
        """Test that close() can be called multiple times safely."""
        with patch("grpc.aio.insecure_channel", return_value=mock_channel):
            with patch(
                "app.grpc.client.processing_pb2_grpc.ProcessingServiceStub",
                return_value=mock_stub,
            ):
                client = ProcessingClient("localhost:50051")
                await client.connect()

                # Close twice should not raise
                await client.close()
                await client.close()

                assert not client._connected


class TestProcessingClientUrlSubmission:
    """Test URL submission and streaming."""

    @pytest.mark.asyncio
    async def test_submit_url_success(self, mock_channel, mock_stub):
        """Test successful URL submission and streaming updates."""
        # Create mock updates
        updates = [
            processing_pb2.ProcessingUpdate(
                request_id=1,
                status=processing_pb2.ProcessingStatus.ProcessingStatus_PENDING,
                stage=processing_pb2.ProcessingStage.ProcessingStage_QUEUED,
                message="Request accepted",
                progress=0.0,
            ),
            processing_pb2.ProcessingUpdate(
                request_id=1,
                status=processing_pb2.ProcessingStatus.ProcessingStatus_PROCESSING,
                stage=processing_pb2.ProcessingStage.ProcessingStage_EXTRACTION,
                message="Extracting content",
                progress=0.2,
            ),
            processing_pb2.ProcessingUpdate(
                request_id=1,
                status=processing_pb2.ProcessingStatus.ProcessingStatus_COMPLETED,
                stage=processing_pb2.ProcessingStage.ProcessingStage_DONE,
                message="Processing complete",
                progress=1.0,
                summary_id=42,
            ),
        ]

        mock_stub.SubmitUrl = MagicMock(return_value=async_generator(updates))

        with patch("grpc.aio.insecure_channel", return_value=mock_channel):
            with patch(
                "app.grpc.client.processing_pb2_grpc.ProcessingServiceStub",
                return_value=mock_stub,
            ):
                client = ProcessingClient("localhost:50051")
                await client.connect()

                received_updates = []
                async for update in client.submit_url("https://example.com"):
                    received_updates.append(update)

                assert len(received_updates) == 3
                assert received_updates[0].status == "PENDING"
                assert received_updates[1].status == "PROCESSING"
                assert received_updates[2].status == "COMPLETED"
                assert received_updates[2].summary_id == 42

    @pytest.mark.asyncio
    async def test_submit_url_with_parameters(self, mock_channel, mock_stub):
        """Test URL submission with language and force_refresh."""
        updates = [
            processing_pb2.ProcessingUpdate(
                request_id=1,
                status=processing_pb2.ProcessingStatus.ProcessingStatus_COMPLETED,
                stage=processing_pb2.ProcessingStage.ProcessingStage_DONE,
                message="Done",
                progress=1.0,
            ),
        ]

        mock_stub.SubmitUrl = MagicMock(return_value=async_generator(updates))

        with patch("grpc.aio.insecure_channel", return_value=mock_channel):
            with patch(
                "app.grpc.client.processing_pb2_grpc.ProcessingServiceStub",
                return_value=mock_stub,
            ):
                client = ProcessingClient("localhost:50051")
                await client.connect()

                async for _ in client.submit_url(
                    "https://example.com", language="ru", force_refresh=True
                ):
                    pass

                # Verify the stub was called with correct parameters
                call_args = mock_stub.SubmitUrl.call_args
                assert call_args is not None
                request = call_args[0][0]
                assert request.url == "https://example.com"
                assert request.language == "ru"
                assert request.force_refresh is True

    @pytest.mark.asyncio
    async def test_submit_url_invalid_argument_error(self, mock_channel, mock_stub):
        """Test handling of invalid URL error."""
        rpc_error = grpc.RpcError()
        rpc_error.code = MagicMock(return_value=grpc.StatusCode.INVALID_ARGUMENT)
        rpc_error.details = MagicMock(return_value="URL is required")
        mock_stub.SubmitUrl = MagicMock(side_effect=rpc_error)

        with patch("grpc.aio.insecure_channel", return_value=mock_channel):
            with patch(
                "app.grpc.client.processing_pb2_grpc.ProcessingServiceStub",
                return_value=mock_stub,
            ):
                client = ProcessingClient("localhost:50051")
                await client.connect()

                with pytest.raises(ValidationError) as exc_info:
                    async for _ in client.submit_url(""):
                        pass

                assert "Invalid URL" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_submit_url_deadline_exceeded_error(self, mock_channel, mock_stub):
        """Test handling of timeout error."""
        rpc_error = grpc.RpcError()
        rpc_error.code = MagicMock(return_value=grpc.StatusCode.DEADLINE_EXCEEDED)
        rpc_error.details = MagicMock(return_value="Deadline exceeded")
        mock_stub.SubmitUrl = MagicMock(side_effect=rpc_error)

        with patch("grpc.aio.insecure_channel", return_value=mock_channel):
            with patch(
                "app.grpc.client.processing_pb2_grpc.ProcessingServiceStub",
                return_value=mock_stub,
            ):
                client = ProcessingClient("localhost:50051")
                await client.connect()

                with pytest.raises(TimeoutError) as exc_info:
                    async for _ in client.submit_url("https://example.com"):
                        pass

                assert "timed out" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_submit_url_unavailable_error(self, mock_channel, mock_stub):
        """Test handling of server unavailable error."""
        rpc_error = grpc.RpcError()
        rpc_error.code = MagicMock(return_value=grpc.StatusCode.UNAVAILABLE)
        rpc_error.details = MagicMock(return_value="Server unavailable")
        mock_stub.SubmitUrl = MagicMock(side_effect=rpc_error)

        with patch("grpc.aio.insecure_channel", return_value=mock_channel):
            with patch(
                "app.grpc.client.processing_pb2_grpc.ProcessingServiceStub",
                return_value=mock_stub,
            ):
                client = ProcessingClient("localhost:50051")
                await client.connect()

                with pytest.raises(ConnectionError) as exc_info:
                    async for _ in client.submit_url("https://example.com"):
                        pass

                assert "unavailable" in str(exc_info.value)


class TestProcessingClientHighLevel:
    """Test high-level process_url method."""

    @pytest.mark.asyncio
    async def test_process_url_success(self, mock_channel, mock_stub):
        """Test successful URL processing with result."""
        updates = [
            processing_pb2.ProcessingUpdate(
                request_id=1,
                status=processing_pb2.ProcessingStatus.ProcessingStatus_PENDING,
                stage=processing_pb2.ProcessingStage.ProcessingStage_QUEUED,
                message="Request accepted",
                progress=0.0,
            ),
            processing_pb2.ProcessingUpdate(
                request_id=1,
                status=processing_pb2.ProcessingStatus.ProcessingStatus_COMPLETED,
                stage=processing_pb2.ProcessingStage.ProcessingStage_DONE,
                message="Complete",
                progress=1.0,
                summary_id=123,
            ),
        ]

        mock_stub.SubmitUrl = MagicMock(return_value=async_generator(updates))

        with patch("grpc.aio.insecure_channel", return_value=mock_channel):
            with patch(
                "app.grpc.client.processing_pb2_grpc.ProcessingServiceStub",
                return_value=mock_stub,
            ):
                client = ProcessingClient("localhost:50051")
                result = await client.process_url("https://example.com")

                assert isinstance(result, ProcessingResult)
                assert result.is_success
                assert result.request_id == 1
                assert result.summary_id == 123
                assert result.status == "COMPLETED"

    @pytest.mark.asyncio
    async def test_process_url_failure(self, mock_channel, mock_stub):
        """Test URL processing failure."""
        updates = [
            processing_pb2.ProcessingUpdate(
                request_id=1,
                status=processing_pb2.ProcessingStatus.ProcessingStatus_FAILED,
                stage=processing_pb2.ProcessingStage.ProcessingStage_UNSPECIFIED,
                message="Processing failed",
                progress=1.0,
                error="Extraction failed",
            ),
        ]

        mock_stub.SubmitUrl = MagicMock(return_value=async_generator(updates))

        with patch("grpc.aio.insecure_channel", return_value=mock_channel):
            with patch(
                "app.grpc.client.processing_pb2_grpc.ProcessingServiceStub",
                return_value=mock_stub,
            ):
                client = ProcessingClient("localhost:50051")

                with pytest.raises(ProcessingFailedError) as exc_info:
                    await client.process_url("https://example.com")

                assert "failed" in str(exc_info.value).lower()
                assert exc_info.value.result.status == "FAILED"
                assert exc_info.value.result.error == "Extraction failed"

    @pytest.mark.asyncio
    async def test_process_url_with_progress_callback(self, mock_channel, mock_stub):
        """Test progress callback is called during processing."""
        updates = [
            processing_pb2.ProcessingUpdate(
                request_id=1,
                status=processing_pb2.ProcessingStatus.ProcessingStatus_PENDING,
                stage=processing_pb2.ProcessingStage.ProcessingStage_QUEUED,
                message="Request accepted",
                progress=0.0,
            ),
            processing_pb2.ProcessingUpdate(
                request_id=1,
                status=processing_pb2.ProcessingStatus.ProcessingStatus_COMPLETED,
                stage=processing_pb2.ProcessingStage.ProcessingStage_DONE,
                message="Complete",
                progress=1.0,
                summary_id=42,
            ),
        ]

        mock_stub.SubmitUrl = MagicMock(return_value=async_generator(updates))

        progress_updates = []

        def callback(update):
            progress_updates.append(update)

        with patch("grpc.aio.insecure_channel", return_value=mock_channel):
            with patch(
                "app.grpc.client.processing_pb2_grpc.ProcessingServiceStub",
                return_value=mock_stub,
            ):
                client = ProcessingClient("localhost:50051")
                await client.process_url("https://example.com", progress_callback=callback)

                assert len(progress_updates) == 2
                assert progress_updates[0].progress == 0.0
                assert progress_updates[1].progress == 1.0

    @pytest.mark.asyncio
    async def test_process_url_no_updates(self, mock_channel, mock_stub):
        """Test handling when no updates are received."""
        mock_stub.SubmitUrl = MagicMock(return_value=async_generator([]))

        with patch("grpc.aio.insecure_channel", return_value=mock_channel):
            with patch(
                "app.grpc.client.processing_pb2_grpc.ProcessingServiceStub",
                return_value=mock_stub,
            ):
                client = ProcessingClient("localhost:50051")

                with pytest.raises(ProcessingClientError) as exc_info:
                    await client.process_url("https://example.com")

                assert "No updates received" in str(exc_info.value)


class TestProcessingClientBatch:
    """Test batch URL processing."""

    @pytest.mark.asyncio
    async def test_process_urls_success(self, mock_channel, mock_stub):
        """Test successful batch processing."""

        def create_updates(request_id, summary_id):
            return [
                processing_pb2.ProcessingUpdate(
                    request_id=request_id,
                    status=processing_pb2.ProcessingStatus.ProcessingStatus_COMPLETED,
                    stage=processing_pb2.ProcessingStage.ProcessingStage_DONE,
                    message="Complete",
                    progress=1.0,
                    summary_id=summary_id,
                ),
            ]

        # Mock stub to return different results for different calls
        call_count = 0

        def mock_submit(request, timeout=None):
            nonlocal call_count
            call_count += 1
            return async_generator(create_updates(call_count, call_count * 100))

        mock_stub.SubmitUrl = MagicMock(side_effect=mock_submit)

        with patch("grpc.aio.insecure_channel", return_value=mock_channel):
            with patch(
                "app.grpc.client.processing_pb2_grpc.ProcessingServiceStub",
                return_value=mock_stub,
            ):
                client = ProcessingClient("localhost:50051")
                urls = [
                    "https://example1.com",
                    "https://example2.com",
                    "https://example3.com",
                ]

                results = await client.process_urls(urls, max_concurrent=2)

                assert len(results) == 3
                for i, result in enumerate(results):
                    assert result.is_success
                    assert result.summary_id == (i + 1) * 100

    @pytest.mark.asyncio
    async def test_process_urls_with_failures(self, mock_channel, mock_stub):
        """Test batch processing with some failures."""

        def create_failure_updates(request_id):
            return [
                processing_pb2.ProcessingUpdate(
                    request_id=request_id,
                    status=processing_pb2.ProcessingStatus.ProcessingStatus_FAILED,
                    stage=processing_pb2.ProcessingStage.ProcessingStage_UNSPECIFIED,
                    message="Failed",
                    progress=1.0,
                    error="Network error",
                ),
            ]

        def create_success_updates(request_id):
            return [
                processing_pb2.ProcessingUpdate(
                    request_id=request_id,
                    status=processing_pb2.ProcessingStatus.ProcessingStatus_COMPLETED,
                    stage=processing_pb2.ProcessingStage.ProcessingStage_DONE,
                    message="Complete",
                    progress=1.0,
                    summary_id=999,
                ),
            ]

        call_count = 0

        def mock_submit(request, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                # Second URL fails
                return async_generator(create_failure_updates(call_count))
            return async_generator(create_success_updates(call_count))

        mock_stub.SubmitUrl = MagicMock(side_effect=mock_submit)

        with patch("grpc.aio.insecure_channel", return_value=mock_channel):
            with patch(
                "app.grpc.client.processing_pb2_grpc.ProcessingServiceStub",
                return_value=mock_stub,
            ):
                client = ProcessingClient("localhost:50051")
                urls = [
                    "https://example1.com",
                    "https://example2.com",
                    "https://example3.com",
                ]

                results = await client.process_urls(urls, max_concurrent=3)

                assert len(results) == 3
                assert results[0].is_success
                assert not results[1].is_success
                assert "Network error" in results[1].error
                assert results[2].is_success

    @pytest.mark.asyncio
    async def test_process_urls_with_progress_callback(self, mock_channel, mock_stub):
        """Test batch progress callback."""
        updates = [
            processing_pb2.ProcessingUpdate(
                request_id=1,
                status=processing_pb2.ProcessingStatus.ProcessingStatus_COMPLETED,
                stage=processing_pb2.ProcessingStage.ProcessingStage_DONE,
                message="Complete",
                progress=1.0,
                summary_id=1,
            ),
        ]

        # Return a fresh generator for each call
        mock_stub.SubmitUrl = MagicMock(
            side_effect=lambda *args, **kwargs: async_generator(updates)
        )

        progress_calls = []

        def callback(url, update):
            progress_calls.append((url, update))

        with patch("grpc.aio.insecure_channel", return_value=mock_channel):
            with patch(
                "app.grpc.client.processing_pb2_grpc.ProcessingServiceStub",
                return_value=mock_stub,
            ):
                client = ProcessingClient("localhost:50051")
                urls = ["https://example1.com", "https://example2.com"]

                await client.process_urls(urls, max_concurrent=2, progress_callback=callback)

                assert len(progress_calls) == 2
                assert progress_calls[0][0] == "https://example1.com"
                assert progress_calls[1][0] == "https://example2.com"


class TestProcessingClientHelper:
    """Test helper functions."""

    @pytest.mark.asyncio
    async def test_processing_client_context_manager(self, mock_channel, mock_stub):
        """Test the processing_client helper context manager."""
        with patch("grpc.aio.insecure_channel", return_value=mock_channel):
            with patch(
                "app.grpc.client.processing_pb2_grpc.ProcessingServiceStub",
                return_value=mock_stub,
            ):
                async with processing_client("localhost:50051") as client:
                    assert isinstance(client, ProcessingClient)
                    assert client._connected


class TestSyncProcessingClient:
    """Test synchronous client wrapper."""

    def test_sync_client_process_url_success(self, mock_channel, mock_stub):
        """Test synchronous URL processing."""
        updates = [
            processing_pb2.ProcessingUpdate(
                request_id=1,
                status=processing_pb2.ProcessingStatus.ProcessingStatus_COMPLETED,
                stage=processing_pb2.ProcessingStage.ProcessingStage_DONE,
                message="Complete",
                progress=1.0,
                summary_id=42,
            ),
        ]

        mock_stub.SubmitUrl = MagicMock(return_value=async_generator(updates))

        with patch("grpc.aio.insecure_channel", return_value=mock_channel):
            with patch(
                "app.grpc.client.processing_pb2_grpc.ProcessingServiceStub",
                return_value=mock_stub,
            ):
                with SyncProcessingClient("localhost:50051") as client:
                    result = client.process_url("https://example.com")

                    assert isinstance(result, ProcessingResult)
                    assert result.is_success
                    assert result.summary_id == 42

    def test_sync_client_process_urls(self, mock_channel, mock_stub):
        """Test synchronous batch processing."""
        updates = [
            processing_pb2.ProcessingUpdate(
                request_id=1,
                status=processing_pb2.ProcessingStatus.ProcessingStatus_COMPLETED,
                stage=processing_pb2.ProcessingStage.ProcessingStage_DONE,
                message="Complete",
                progress=1.0,
                summary_id=100,
            ),
        ]

        # Return a fresh generator for each call
        mock_stub.SubmitUrl = MagicMock(
            side_effect=lambda *args, **kwargs: async_generator(updates)
        )

        with patch("grpc.aio.insecure_channel", return_value=mock_channel):
            with patch(
                "app.grpc.client.processing_pb2_grpc.ProcessingServiceStub",
                return_value=mock_stub,
            ):
                with SyncProcessingClient("localhost:50051") as client:
                    results = client.process_urls(
                        ["https://example1.com", "https://example2.com"],
                        max_concurrent=2,
                    )

                    assert len(results) == 2
                    assert all(r.is_success for r in results)


class TestProcessingResult:
    """Test ProcessingResult dataclass."""

    def test_is_success_true(self):
        """Test is_success returns True for completed without error."""
        result = ProcessingResult(
            request_id=1,
            status="COMPLETED",
            stage="DONE",
            summary_id=42,
            error=None,
        )
        assert result.is_success

    def test_is_success_false_with_error(self):
        """Test is_success returns False when error present."""
        result = ProcessingResult(
            request_id=1,
            status="COMPLETED",
            stage="DONE",
            summary_id=None,
            error="Something went wrong",
        )
        assert not result.is_success

    def test_is_success_false_wrong_status(self):
        """Test is_success returns False for non-completed status."""
        result = ProcessingResult(
            request_id=1,
            status="FAILED",
            stage="UNSPECIFIED",
            error=None,
        )
        assert not result.is_success


class TestProcessingUpdate:
    """Test ProcessingUpdate dataclass."""

    def test_update_creation(self):
        """Test creating ProcessingUpdate instance."""
        update = ProcessingUpdate(
            request_id=1,
            status="PROCESSING",
            stage="EXTRACTION",
            message="Extracting content",
            progress=0.5,
            summary_id=None,
            error=None,
        )

        assert update.request_id == 1
        assert update.status == "PROCESSING"
        assert update.progress == 0.5


# Helper function to create async generators from lists
async def async_generator(items):
    """Helper to convert list to async generator."""
    for item in items:
        yield item
