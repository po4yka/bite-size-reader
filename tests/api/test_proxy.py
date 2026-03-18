from unittest.mock import AsyncMock, patch

import pytest
from httpx import RequestError, Response

from app.api.exceptions import ExternalAPIError, ResourceNotFoundError, ValidationError
from app.api.routers.proxy import proxy_image


async def _aiter_bytes(chunks: list[bytes]):
    for chunk in chunks:
        yield chunk


@pytest.mark.asyncio
async def test_proxy_image_success():
    """Test successful image proxying."""
    mock_response = AsyncMock(spec=Response)
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "image/jpeg"}
    mock_response.aiter_bytes = lambda: _aiter_bytes([b"fake", b"image"])
    mock_response.aclose = AsyncMock()

    # Mock the context manager behavior of AsyncClient
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.send.return_value = mock_response

        response = await proxy_image("https://example.com/image.jpg")

        assert response.status_code == 200
        assert response.media_type == "image/jpeg"
        assert response.body == b"fakeimage"


@pytest.mark.asyncio
async def test_proxy_image_invalid_scheme():
    """Test rejection of non-http/https URLs."""
    with pytest.raises(ValidationError):
        await proxy_image("ftp://example.com/image.jpg")


@pytest.mark.asyncio
async def test_proxy_image_not_found():
    """Test handling of 404 from upstream."""
    mock_response = AsyncMock(spec=Response)
    mock_response.status_code = 404
    mock_response.aclose = AsyncMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.send.return_value = mock_response

        with pytest.raises(ResourceNotFoundError):
            await proxy_image("https://example.com/missing.jpg")


@pytest.mark.asyncio
async def test_proxy_image_not_an_image():
    """Test rejection of non-image content types."""
    mock_response = AsyncMock(spec=Response)
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "text/html"}
    mock_response.aclose = AsyncMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.send.return_value = mock_response

        with pytest.raises(ValidationError):
            await proxy_image("https://example.com/page.html")


@pytest.mark.asyncio
async def test_proxy_image_request_error():
    """Test handling of network errors."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.send.side_effect = RequestError("Connection failed")

        with pytest.raises(ExternalAPIError):
            await proxy_image("https://example.com/image.jpg")


@pytest.mark.asyncio
async def test_proxy_image_rejects_declared_too_large_content():
    """Declared content-length above limit should be rejected with 413."""
    mock_response = AsyncMock(spec=Response)
    mock_response.status_code = 200
    mock_response.headers = {
        "content-type": "image/jpeg",
        "content-length": str(11 * 1024 * 1024),
    }
    mock_response.aclose = AsyncMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.send.return_value = mock_response

        with pytest.raises(ValidationError):
            await proxy_image("https://example.com/huge.jpg")


@pytest.mark.asyncio
async def test_proxy_image_rejects_stream_too_large_content():
    """Streaming content above limit should be rejected with 413."""
    ten_mb = 10 * 1024 * 1024
    mock_response = AsyncMock(spec=Response)
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "image/jpeg"}
    mock_response.aiter_bytes = lambda: _aiter_bytes([b"x" * ten_mb, b"y"])
    mock_response.aclose = AsyncMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.send.return_value = mock_response

        with pytest.raises(ValidationError):
            await proxy_image("https://example.com/huge-stream.jpg")
