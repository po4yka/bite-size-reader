"""Runtime tuning helpers for scraper providers."""

from __future__ import annotations

from urllib.parse import urlparse

PROFILE_TIMEOUT_MULTIPLIERS: dict[str, float] = {
    "fast": 0.75,
    "balanced": 1.0,
    "robust": 1.35,
}

_ALLOWED_PROFILES = frozenset(PROFILE_TIMEOUT_MULTIPLIERS)


def normalize_profile(profile: str) -> str:
    value = profile.strip().lower()
    if value not in _ALLOWED_PROFILES:
        return "balanced"
    return value


def profile_timeout_multiplier(profile: str) -> float:
    normalized = normalize_profile(profile)
    return PROFILE_TIMEOUT_MULTIPLIERS[normalized]


def profile_retry_budget(base_retries: int, profile: str) -> int:
    normalized = normalize_profile(profile)
    retries = max(0, int(base_retries))
    if normalized == "fast":
        return min(retries, 1)
    if normalized == "robust":
        return min(retries + 1, 5)
    return retries


def normalize_hosts(hosts: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    normalized = {str(host).strip().lower() for host in hosts if str(host).strip()}
    return tuple(sorted(normalized))


def is_js_heavy_url(url: str, js_heavy_hosts: tuple[str, ...] | list[str]) -> bool:
    host = _extract_host(url)
    if not host:
        return False
    allowed = set(normalize_hosts(tuple(js_heavy_hosts)))
    if host in allowed:
        return True
    return any(host.endswith(f".{suffix}") for suffix in allowed)


def tuned_provider_timeout(
    *,
    base_timeout_sec: float,
    profile: str,
    provider: str,
    url: str,
    js_heavy_hosts: tuple[str, ...] | list[str],
) -> float:
    timeout = max(1.0, float(base_timeout_sec))
    timeout *= profile_timeout_multiplier(profile)

    if is_js_heavy_url(url, js_heavy_hosts):
        if provider == "scrapling":
            timeout *= 0.8
        elif provider in {"playwright", "crawlee"}:
            timeout *= 1.25

    return max(1.0, timeout)


def tuned_firecrawl_wait_for_ms(
    *,
    base_wait_for_ms: int,
    url: str,
    js_heavy_hosts: tuple[str, ...] | list[str],
) -> int:
    wait_for_ms = max(0, int(base_wait_for_ms))
    if wait_for_ms <= 0:
        return 0
    if is_js_heavy_url(url, js_heavy_hosts):
        return min(10_000, int(wait_for_ms * 1.3))
    return wait_for_ms


def _extract_host(url: str) -> str | None:
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return None
    host = (parsed.hostname or "").strip().lower()
    return host or None
