"""
Proxy endpoints for external resources.
"""

import httpx
from fastapi import APIRouter, HTTPException, Query
from starlette.responses import StreamingResponse

from app.core.logging_utils import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/image")
async def proxy_image(url: str = Query(..., description="URL of the image to proxy")):
    """
    Proxy an image from a remote URL.

    This endpoint fetches an image from the specified URL and streams it back to the client.
    It helps bypass CORs issues, mixed content warnings (loading HTTP images on HTTPS sites),
    and potential hotlink protection.
    """
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid URL scheme")

    try:
        # Use a real browser User-Agent to avoid getting blocked by some servers
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            req = client.build_request("GET", url, headers=headers)
            resp = await client.send(req, stream=True)

            if resp.status_code >= 400:
                logger.warning(f"Failed to fetch image: {url} - Status: {resp.status_code}")
                raise HTTPException(status_code=404, detail="Image not found or inaccessible")

            content_type = resp.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                logger.warning(f"URL is not an image: {url} - Type: {content_type}")
                raise HTTPException(status_code=400, detail="URL does not point to an image")

            return StreamingResponse(
                resp.aiter_bytes(),
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=86400",  # Cache for 1 day
                },
            )

    except httpx.RequestError as e:
        logger.error(f"Proxy request error for {url}: {e}")
        raise HTTPException(status_code=502, detail="Failed to fetch upstream image") from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected proxy error: {e}")
        raise HTTPException(status_code=500, detail="Internal proxy error") from e
