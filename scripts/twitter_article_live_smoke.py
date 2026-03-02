"""Manual live smoke checks for X Article link resolution and extraction.

This script is optional and is not intended for CI gating. It runs the same
two-step strategy used by production extraction:
1) Firecrawl attempt
2) Playwright fallback

Output: one JSON object per URL plus a final JSON summary line.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# ruff: noqa: E402


# Allow running via `python scripts/twitter_article_live_smoke.py` from any cwd.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.adapters.content.quality_filters import detect_low_value_content
from app.adapters.external.firecrawl_parser import FirecrawlClient
from app.adapters.twitter.article_link_resolver import resolve_twitter_article_link
from app.adapters.twitter.article_quality import is_low_quality_article_content
from app.adapters.twitter.playwright_client import scrape_article
from app.core.html_utils import clean_markdown_article_text, html_to_text

logger = logging.getLogger("twitter_article_live_smoke")

_URL_TOKEN_SPLIT_RE = re.compile(r"[\s,]+")


@dataclass
class SmokeResult:
    input_url: str
    final_status: str
    resolution_reason: str
    article_id: str | None
    article_resolved_url: str | None
    article_canonical_url: str | None
    article_extraction_stage: str | None
    content_length: int
    failure_reason: str | None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _split_url_tokens(raw: str) -> list[str]:
    return [token.strip() for token in _URL_TOKEN_SPLIT_RE.split(raw) if token.strip()]


def _collect_urls(cli_urls: list[str], urls_arg: str, urls_env: str) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []

    for item in cli_urls:
        for token in _split_url_tokens(item):
            if token not in seen:
                seen.add(token)
                ordered.append(token)

    for token in _split_url_tokens(urls_arg):
        if token not in seen:
            seen.add(token)
            ordered.append(token)

    for token in _split_url_tokens(urls_env):
        if token not in seen:
            seen.add(token)
            ordered.append(token)

    return ordered


_is_low_quality_article_content = is_low_quality_article_content


def _build_firecrawl_client(api_key: str, timeout_sec: float) -> FirecrawlClient | None:
    key = api_key.strip()
    if not key:
        return None
    return FirecrawlClient(
        api_key=key,
        timeout_sec=max(10, int(timeout_sec)),
        max_retries=1,
        wait_for_ms=3_000,
    )


async def _extract_article_with_firecrawl(
    firecrawl: FirecrawlClient, article_url: str
) -> tuple[str | None, str]:
    crawl = await firecrawl.scrape_markdown(article_url)
    if crawl.status != "ok":
        return None, f"status:{crawl.status}"

    quality_issue = detect_low_value_content(crawl)
    if quality_issue:
        reason = str(quality_issue.get("reason") or "quality_gate_failed")
        return None, f"quality:{reason}"

    content = ""
    if crawl.content_markdown and crawl.content_markdown.strip():
        content = clean_markdown_article_text(crawl.content_markdown)
    elif crawl.content_html and crawl.content_html.strip():
        content = html_to_text(crawl.content_html)
    if not content.strip():
        return None, "empty_content"

    if _is_low_quality_article_content(content):
        return None, "ui_or_login"
    return content, "ok"


async def _extract_article_with_playwright(
    article_url: str,
    *,
    cookies_path: Path | None,
    headless: bool,
    timeout_sec: float,
) -> tuple[str | None, dict[str, Any], str]:
    timeout_ms = max(30_000, int(timeout_sec * 1000))
    article_data = await scrape_article(
        article_url,
        cookies_path=cookies_path,
        headless=headless,
        timeout_ms=timeout_ms,
    )
    content = str(article_data.get("content") or "").strip()
    if not content:
        return None, article_data, "empty_content"
    if _is_low_quality_article_content(content):
        return None, article_data, "ui_or_login"
    return content, article_data, "ok"


async def _run_one(
    input_url: str,
    *,
    timeout_sec: float,
    firecrawl: FirecrawlClient | None,
    cookies_path: Path | None,
    headless: bool,
) -> SmokeResult:
    resolution = await resolve_twitter_article_link(input_url, timeout_s=timeout_sec)
    result = SmokeResult(
        input_url=input_url,
        final_status="failed",
        resolution_reason=resolution.reason,
        article_id=resolution.article_id,
        article_resolved_url=resolution.resolved_url,
        article_canonical_url=resolution.canonical_url,
        article_extraction_stage=None,
        content_length=0,
        failure_reason=None,
    )

    if not resolution.is_article:
        if resolution.reason == "resolve_failed":
            result.final_status = "failed"
            result.failure_reason = "resolve_failed"
        else:
            result.final_status = "not_article"
        return result

    article_target = resolution.canonical_url or resolution.resolved_url or input_url

    firecrawl_reason = "not_attempted"
    if firecrawl is not None:
        try:
            firecrawl_content, firecrawl_reason = await _extract_article_with_firecrawl(
                firecrawl, article_target
            )
            if firecrawl_content:
                result.final_status = "success"
                result.article_extraction_stage = "firecrawl"
                result.content_length = len(firecrawl_content)
                return result
        except Exception as exc:
            firecrawl_reason = f"exception:{type(exc).__name__}"
    else:
        firecrawl_reason = "firecrawl_missing_api_key"

    try:
        pw_content, pw_data, pw_reason = await _extract_article_with_playwright(
            article_target,
            cookies_path=cookies_path,
            headless=headless,
            timeout_sec=timeout_sec,
        )
    except Exception as exc:
        result.failure_reason = (
            f"firecrawl={firecrawl_reason};playwright_exception:{type(exc).__name__}:{exc}"
        )
        return result

    if pw_content:
        result.final_status = "success"
        result.article_extraction_stage = "playwright"
        result.content_length = len(pw_content)
        result.article_resolved_url = str(
            pw_data.get("finalUrl") or result.article_resolved_url or ""
        )
        result.article_canonical_url = str(
            pw_data.get("canonicalUrl") or result.article_canonical_url or ""
        )
        if not result.article_resolved_url:
            result.article_resolved_url = None
        if not result.article_canonical_url:
            result.article_canonical_url = None
        return result

    result.failure_reason = f"firecrawl={firecrawl_reason};playwright={pw_reason}"
    return result


async def run_smoke(
    *,
    urls: list[str],
    timeout_sec: float,
    firecrawl_api_key: str,
    cookies_path: Path | None,
    headless: bool,
) -> tuple[list[SmokeResult], int]:
    firecrawl = _build_firecrawl_client(firecrawl_api_key, timeout_sec)
    exit_code = 0
    results: list[SmokeResult] = []
    try:
        for url in urls:
            result = await _run_one(
                url,
                timeout_sec=timeout_sec,
                firecrawl=firecrawl,
                cookies_path=cookies_path,
                headless=headless,
            )
            if result.final_status == "failed":
                exit_code = 1
            results.append(result)
    finally:
        if firecrawl is not None:
            await firecrawl.aclose()

    return results, exit_code


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manual live smoke checks for X article link handling",
    )
    parser.add_argument(
        "--url",
        action="append",
        default=[],
        help="URL to test (can be repeated).",
    )
    parser.add_argument(
        "--urls",
        default="",
        help=(
            "Comma/newline separated URLs to test. "
            "Can also be provided via TWITTER_ARTICLE_SMOKE_URLS."
        ),
    )
    parser.add_argument(
        "--cookies-path",
        default=os.getenv("TWITTER_COOKIES_PATH", "/data/twitter_cookies.txt"),
        help="Path to Netscape cookies.txt for Playwright fallback.",
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=float(os.getenv("TWITTER_ARTICLE_RESOLUTION_TIMEOUT_SEC", "5")),
        help="Resolution and extraction timeout in seconds.",
    )
    parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=_env_bool("TWITTER_HEADLESS", True),
        help="Run Playwright in headless mode.",
    )
    parser.add_argument(
        "--firecrawl-api-key",
        default=os.getenv("FIRECRAWL_API_KEY", ""),
        help="Firecrawl API key (falls back to FIRECRAWL_API_KEY env var).",
    )
    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = _build_parser()
    args = parser.parse_args()

    urls_env = os.getenv("TWITTER_ARTICLE_SMOKE_URLS", "")
    urls = _collect_urls(args.url, args.urls, urls_env)
    if not urls:
        parser.error("No URLs provided. Use --url/--urls or TWITTER_ARTICLE_SMOKE_URLS.")

    if not _env_bool("TWITTER_ARTICLE_LIVE_SMOKE_ENABLED", False):
        logger.warning(
            "TWITTER_ARTICLE_LIVE_SMOKE_ENABLED is false; running manual smoke check anyway."
        )

    cookies_path = Path(args.cookies_path).expanduser() if args.cookies_path else None
    if cookies_path is not None and not cookies_path.exists():
        logger.warning(
            "Cookies path does not exist: %s (Playwright may fail on gated articles)", cookies_path
        )
        cookies_path = None

    results, exit_code = asyncio.run(
        run_smoke(
            urls=urls,
            timeout_sec=max(0.1, float(args.timeout_sec)),
            firecrawl_api_key=str(args.firecrawl_api_key or ""),
            cookies_path=cookies_path,
            headless=bool(args.headless),
        )
    )

    for item in results:
        print(json.dumps(asdict(item), ensure_ascii=False))

    summary = {
        "type": "summary",
        "total": len(results),
        "success": sum(1 for item in results if item.final_status == "success"),
        "failed": sum(1 for item in results if item.final_status == "failed"),
        "not_article": sum(1 for item in results if item.final_status == "not_article"),
    }
    print(json.dumps(summary, ensure_ascii=False))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
