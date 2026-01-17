"""
Proxy endpoints for external resources.
"""

import socket
from ipaddress import ip_address, ip_network
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query
from starlette.responses import StreamingResponse

from app.core.logging_utils import get_logger

logger = get_logger(__name__)
router = APIRouter()

# Private/internal IP ranges that should be blocked to prevent SSRF
BLOCKED_NETWORKS = [
    ip_network("10.0.0.0/8"),  # Private Class A
    ip_network("172.16.0.0/12"),  # Private Class B
    ip_network("192.168.0.0/16"),  # Private Class C
    ip_network("127.0.0.0/8"),  # Loopback
    ip_network("169.254.0.0/16"),  # Link-local / AWS metadata
    ip_network("0.0.0.0/8"),  # Current network
    ip_network("100.64.0.0/10"),  # Carrier-grade NAT
    ip_network("192.0.0.0/24"),  # IETF Protocol Assignments
    ip_network("192.0.2.0/24"),  # TEST-NET-1
    ip_network("198.51.100.0/24"),  # TEST-NET-2
    ip_network("203.0.113.0/24"),  # TEST-NET-3
    ip_network("224.0.0.0/4"),  # Multicast
    ip_network("240.0.0.0/4"),  # Reserved
    ip_network("255.255.255.255/32"),  # Broadcast
    ip_network("::1/128"),  # IPv6 loopback
    ip_network("fc00::/7"),  # IPv6 private
    ip_network("fe80::/10"),  # IPv6 link-local
]


def _resolve_host_ips(hostname: str) -> list[str]:
    """Resolve hostname to IP addresses (IPv4/IPv6)."""
    addresses: list[str] = []
    for info in socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP):
        addr = str(info[4][0])
        if addr not in addresses:
            addresses.append(addr)
    return addresses


def _is_url_safe(url: str) -> bool:
    """
    Check if URL resolves to a public IP address.

    Returns False for private networks, localhost, and cloud metadata endpoints.
    """
    try:
        hostname = urlparse(url).hostname
        if not hostname:
            return False

        if hostname.lower() in ("localhost", "localhost.localdomain"):
            return False

        # Resolve hostname to IPs (IPv4/IPv6) and check against blocked networks
        resolved_ips = _resolve_host_ips(hostname)
        if not resolved_ips:
            return False

        for resolved in resolved_ips:
            ip_obj = ip_address(resolved)
            if any(ip_obj in network for network in BLOCKED_NETWORKS):
                return False
        return True
    except (socket.gaierror, ValueError, OSError):
        # DNS resolution failed or invalid IP - block for safety
        return False


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

        async with httpx.AsyncClient(follow_redirects=False, timeout=10.0) as client:
            max_redirects = 5
            current_url = url
            for _ in range(max_redirects + 1):
                # SSRF protection: block requests to internal/private networks
                if not _is_url_safe(current_url):
                    logger.warning(f"Blocked SSRF attempt to internal address: {current_url}")
                    raise HTTPException(status_code=403, detail="URL resolves to blocked address")

                req = client.build_request("GET", current_url, headers=headers)
                resp = await client.send(req, stream=True)

                if resp.status_code in {301, 302, 303, 307, 308}:
                    location = resp.headers.get("location")
                    await resp.aclose()
                    if not location:
                        raise HTTPException(
                            status_code=502, detail="Upstream redirect missing location"
                        )
                    next_url = str(httpx.URL(current_url).join(location))
                    if not next_url.startswith(("http://", "https://")):
                        raise HTTPException(status_code=400, detail="Invalid redirect URL scheme")
                    current_url = next_url
                    continue
                break
            else:
                raise HTTPException(status_code=502, detail="Too many redirects")

            if resp.status_code >= 400:
                logger.warning(f"Failed to fetch image: {current_url} - Status: {resp.status_code}")
                raise HTTPException(status_code=404, detail="Image not found or inaccessible")

            content_type = resp.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                logger.warning(f"URL is not an image: {current_url} - Type: {content_type}")
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
