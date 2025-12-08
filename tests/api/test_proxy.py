from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from httpx import RequestError, Response

from app.api.routers.proxy import proxy_image


@pytest.mark.asyncio
async def test_proxy_image_success():
    """Test successful image proxying."""
    mock_response = AsyncMock(spec=Response)
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "image/jpeg"}
    mock_response.aiter_bytes = AsyncMock(return_value=iter([b"fake", b"image"]))

    # Mock the context manager behavior of AsyncClient
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.send.return_value = mock_response

        response = await proxy_image("https://example.com/image.jpg")

        assert response.status_code == 200
        assert response.media_type == "image/jpeg"
        # Since it's a streaming response, we can't easily check body in unit test without consuming it,
        # but the creation of StreamingResponse indicates success.


@pytest.mark.asyncio
async def test_proxy_image_invalid_scheme():
    """Test rejection of non-http/https URLs."""
    with pytest.raises(HTTPException) as exc:
        await proxy_image("ftp://example.com/image.jpg")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_proxy_image_not_found():
    """Test handling of 404 from upstream."""
    mock_response = AsyncMock(spec=Response)
    mock_response.status_code = 404

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.send.return_value = mock_response

        with pytest.raises(HTTPException) as exc:
            await proxy_image("https://example.com/missing.jpg")
        assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_proxy_image_not_an_image():
    """Test rejection of non-image content types."""
    mock_response = AsyncMock(spec=Response)
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "text/html"}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.send.return_value = mock_response

        with pytest.raises(HTTPException) as exc:
            await proxy_image("https://example.com/page.html")
        assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_proxy_image_request_error():
    """Test handling of network errors."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.send.side_effect = RequestError("Connection failed")

        with pytest.raises(HTTPException) as exc:
            await proxy_image("https://example.com/image.jpg")
        assert exc.value.status_code == 502
