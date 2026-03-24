"""Tests for multi-provider scraper chain, factory, and individual providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.content.scraper.chain import ContentScraperChain
from app.adapters.content.scraper.factory import ContentScraperFactory
from app.adapters.content.scraper.firecrawl_provider import FirecrawlProvider
from app.adapters.external.firecrawl.models import FirecrawlResult
from app.config.scraper import ScraperConfig
from app.core.call_status import CallStatus

from .conftest import make_test_app_config

# ---------------------------------------------------------------------------
# Helpers -- lightweight mock provider (protocol-conformant without MagicMock)
# ---------------------------------------------------------------------------


@dataclass
class _MockProvider:
    """Minimal ContentScraperProtocol-conformant stub."""

    name: str = "mock"
    result: FirecrawlResult | None = None
    exception: Exception | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)
    closed: bool = False

    @property
    def provider_name(self) -> str:
        return self.name

    async def scrape_markdown(
        self,
        url: str,
        *,
        mobile: bool = True,
        request_id: int | None = None,
    ) -> FirecrawlResult:
        self.calls.append({"url": url, "mobile": mobile, "request_id": request_id})
        if self.exception is not None:
            raise self.exception
        assert self.result is not None, "MockProvider.result must be set if no exception"
        return self.result

    async def aclose(self) -> None:
        self.closed = True


def _ok_result(url: str = "https://example.com", markdown: str = "# OK") -> FirecrawlResult:
    return FirecrawlResult(
        status=CallStatus.OK,
        http_status=200,
        content_markdown=markdown,
        source_url=url,
        endpoint="mock",
    )


def _error_result(
    url: str = "https://example.com",
    error: str = "provider failed",
) -> FirecrawlResult:
    return FirecrawlResult(
        status=CallStatus.ERROR,
        error_text=error,
        source_url=url,
        endpoint="mock",
    )


# ===================================================================
# ContentScraperChain tests
# ===================================================================


class TestContentScraperChain:
    """Tests for the ordered-fallback ContentScraperChain."""

    @pytest.mark.asyncio(loop_scope="function")
    async def test_first_provider_succeeds_second_not_called(self):
        """When the first provider returns OK, the second is never invoked."""
        p1 = _MockProvider(name="first", result=_ok_result())
        p2 = _MockProvider(name="second", result=_ok_result(markdown="# Second"))

        chain = ContentScraperChain([p1, p2])
        result = await chain.scrape_markdown("https://example.com")

        assert result.status == "ok"
        assert result.content_markdown == "# OK"
        assert len(p1.calls) == 1
        assert len(p2.calls) == 0

    @pytest.mark.asyncio(loop_scope="function")
    async def test_first_fails_second_succeeds(self):
        """When the first provider returns an error result, the chain tries the second."""
        p1 = _MockProvider(name="first", result=_error_result())
        p2 = _MockProvider(name="second", result=_ok_result(markdown="# Fallback"))

        chain = ContentScraperChain([p1, p2])
        result = await chain.scrape_markdown("https://example.com")

        assert result.status == "ok"
        assert result.content_markdown == "# Fallback"
        assert len(p1.calls) == 1
        assert len(p2.calls) == 1

    @pytest.mark.asyncio(loop_scope="function")
    async def test_first_raises_exception_second_succeeds(self):
        """When the first provider raises, the chain catches and tries the next."""
        p1 = _MockProvider(name="first", exception=RuntimeError("boom"))
        p2 = _MockProvider(name="second", result=_ok_result(markdown="# Recovered"))

        chain = ContentScraperChain([p1, p2])
        result = await chain.scrape_markdown("https://example.com")

        assert result.status == "ok"
        assert result.content_markdown == "# Recovered"
        assert len(p1.calls) == 1
        assert len(p2.calls) == 1

    @pytest.mark.asyncio(loop_scope="function")
    async def test_all_providers_fail_returns_last_result(self):
        """When every provider returns an error, the chain returns the last failed result."""
        p1 = _MockProvider(name="first", result=_error_result(error="p1 fail"))
        p2 = _MockProvider(name="second", result=_error_result(error="p2 fail"))

        chain = ContentScraperChain([p1, p2])
        result = await chain.scrape_markdown("https://example.com")

        assert result.status == "error"
        assert result.error_text == "p2 fail"
        assert len(p1.calls) == 1
        assert len(p2.calls) == 1

    @pytest.mark.asyncio(loop_scope="function")
    async def test_all_providers_raise_returns_synthetic_error(self):
        """When every provider raises an exception, the chain returns a synthetic error."""
        p1 = _MockProvider(name="first", exception=RuntimeError("err1"))
        p2 = _MockProvider(name="second", exception=ValueError("err2"))

        chain = ContentScraperChain([p1, p2])
        result = await chain.scrape_markdown("https://example.com")

        assert result.status == "error"
        assert "All providers failed" in result.error_text
        assert "first: err1" in result.error_text
        assert "second: err2" in result.error_text
        assert result.source_url == "https://example.com"
        assert result.endpoint == "chain"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_single_provider_chain_success(self):
        """A chain with a single provider works correctly on success."""
        p = _MockProvider(name="solo", result=_ok_result(markdown="# Solo"))
        chain = ContentScraperChain([p])
        result = await chain.scrape_markdown("https://example.com")

        assert result.status == "ok"
        assert result.content_markdown == "# Solo"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_single_provider_chain_failure(self):
        """A chain with a single provider returns its error result on failure."""
        p = _MockProvider(name="solo", result=_error_result(error="solo fail"))
        chain = ContentScraperChain([p])
        result = await chain.scrape_markdown("https://example.com")

        assert result.status == "error"
        assert result.error_text == "solo fail"

    def test_empty_providers_raises_value_error(self):
        """Constructing a chain with no providers raises ValueError."""
        with pytest.raises(ValueError, match="at least one provider"):
            ContentScraperChain([])

    @pytest.mark.asyncio(loop_scope="function")
    async def test_aclose_closes_all_providers(self):
        """aclose() calls aclose() on every provider, even if one raises."""
        p1 = _MockProvider(name="first", result=_ok_result())
        p2 = _MockProvider(name="second", result=_ok_result())

        chain = ContentScraperChain([p1, p2])
        await chain.aclose()

        assert p1.closed is True
        assert p2.closed is True

    @pytest.mark.asyncio(loop_scope="function")
    async def test_aclose_tolerates_provider_error(self):
        """aclose() does not propagate if a provider's aclose raises."""

        class _FailClose(_MockProvider):
            async def aclose(self) -> None:
                raise RuntimeError("close error")

        p1 = _FailClose(name="fail_close", result=_ok_result())
        p2 = _MockProvider(name="ok_close", result=_ok_result())

        chain = ContentScraperChain([p1, p2])
        await chain.aclose()  # Should not raise

        assert p2.closed is True

    @pytest.mark.asyncio(loop_scope="function")
    async def test_audit_callback_invoked_on_success(self):
        """The optional audit callback is fired when a provider succeeds."""
        audit_calls: list[tuple[str, str, dict]] = []

        def audit(level: str, event: str, data: dict) -> None:
            audit_calls.append((level, event, data))

        p = _MockProvider(name="audited", result=_ok_result())
        chain = ContentScraperChain([p], audit=audit)
        await chain.scrape_markdown("https://example.com", request_id=42)

        assert len(audit_calls) == 1
        level, event, data = audit_calls[0]
        assert level == "INFO"
        assert event == "scraper_chain_success"
        assert data["provider"] == "audited"
        assert data["url"] == "https://example.com"
        assert data["request_id"] == 42

    @pytest.mark.asyncio(loop_scope="function")
    async def test_audit_callback_not_invoked_on_failure(self):
        """The audit callback is not fired when all providers fail."""
        audit_calls: list[tuple[str, str, dict]] = []

        def audit(level: str, event: str, data: dict) -> None:
            audit_calls.append((level, event, data))

        p = _MockProvider(name="fail", result=_error_result())
        chain = ContentScraperChain([p], audit=audit)
        await chain.scrape_markdown("https://example.com")

        assert len(audit_calls) == 0

    @pytest.mark.asyncio(loop_scope="function")
    async def test_provider_name_is_chain(self):
        """The chain's own provider_name is 'chain'."""
        p = _MockProvider(name="inner", result=_ok_result())
        chain = ContentScraperChain([p])
        assert chain.provider_name == "chain"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_ok_status_but_empty_content_treated_as_failure(self):
        """A result with status='ok' but no content is treated as a failure."""
        empty_ok = FirecrawlResult(
            status="ok",
            http_status=200,
            content_markdown="",
            content_html=None,
            source_url="https://example.com",
            endpoint="mock",
        )
        p1 = _MockProvider(name="empty", result=empty_ok)
        p2 = _MockProvider(name="good", result=_ok_result(markdown="# Content"))

        chain = ContentScraperChain([p1, p2])
        result = await chain.scrape_markdown("https://example.com")

        assert result.status == "ok"
        assert result.content_markdown == "# Content"
        assert len(p1.calls) == 1
        assert len(p2.calls) == 1

    @pytest.mark.asyncio(loop_scope="function")
    async def test_passes_mobile_and_request_id_to_providers(self):
        """The chain forwards mobile and request_id kwargs to providers."""
        p = _MockProvider(name="check", result=_ok_result())
        chain = ContentScraperChain([p])
        await chain.scrape_markdown("https://example.com", mobile=False, request_id=99)

        assert p.calls[0]["mobile"] is False
        assert p.calls[0]["request_id"] == 99

    @pytest.mark.asyncio(loop_scope="function")
    async def test_playwright_success_stops_before_direct_html(self):
        """When Playwright succeeds, lower-priority direct_html is not invoked."""
        scrapling = _MockProvider(name="scrapling", result=_error_result(error="scrapling failed"))
        firecrawl = _MockProvider(name="firecrawl", result=_error_result(error="firecrawl failed"))
        playwright = _MockProvider(name="playwright", result=_ok_result(markdown="# Rendered"))
        direct_html = _MockProvider(name="direct_html", result=_ok_result(markdown="# Direct"))

        chain = ContentScraperChain([scrapling, firecrawl, playwright, direct_html])
        result = await chain.scrape_markdown("https://example.com")

        assert result.status == "ok"
        assert result.content_markdown == "# Rendered"
        assert len(scrapling.calls) == 1
        assert len(firecrawl.calls) == 1
        assert len(playwright.calls) == 1
        assert len(direct_html.calls) == 0

    @pytest.mark.asyncio(loop_scope="function")
    async def test_crawlee_success_stops_before_direct_html(self):
        """When Crawlee succeeds, direct_html is not invoked."""
        scrapling = _MockProvider(name="scrapling", result=_error_result(error="scrapling failed"))
        firecrawl = _MockProvider(name="firecrawl", result=_error_result(error="firecrawl failed"))
        playwright = _MockProvider(
            name="playwright", result=_error_result(error="playwright failed")
        )
        crawlee = _MockProvider(name="crawlee", result=_ok_result(markdown="# Crawlee"))
        direct_html = _MockProvider(name="direct_html", result=_ok_result(markdown="# Direct"))

        chain = ContentScraperChain([scrapling, firecrawl, playwright, crawlee, direct_html])
        result = await chain.scrape_markdown("https://example.com")

        assert result.status == "ok"
        assert result.content_markdown == "# Crawlee"
        assert len(scrapling.calls) == 1
        assert len(firecrawl.calls) == 1
        assert len(playwright.calls) == 1
        assert len(crawlee.calls) == 1
        assert len(direct_html.calls) == 0


# ===================================================================
# ContentScraperFactory tests
# ===================================================================


class TestContentScraperFactory:
    """Tests for the factory that builds a scraper chain from config."""

    def test_default_config_creates_chain_with_scrapling_defuddle_playwright_crawlee_and_direct_html(
        self,
    ):
        """Default config enables scrapling + defuddle + playwright + crawlee + direct_html."""
        cfg = make_test_app_config(scraper=ScraperConfig())

        with (
            patch("app.adapters.content.scraper.factory._build_scrapling") as mock_scrapling,
            patch("app.adapters.content.scraper.factory._build_defuddle") as mock_defuddle,
            patch("app.adapters.content.scraper.factory._build_playwright") as mock_playwright,
            patch("app.adapters.content.scraper.factory._build_crawlee") as mock_crawlee,
            patch("app.adapters.content.scraper.factory._build_direct_html") as mock_direct,
        ):
            mock_scrapling.return_value = _MockProvider(name="scrapling")
            mock_defuddle.return_value = _MockProvider(name="defuddle")
            mock_playwright.return_value = _MockProvider(name="playwright")
            mock_crawlee.return_value = _MockProvider(name="crawlee")
            mock_direct.return_value = _MockProvider(name="direct_html")

            chain = ContentScraperFactory.create_from_config(cfg)

        assert len(chain.providers) == 5
        assert chain.providers[0].provider_name == "scrapling"
        assert chain.providers[1].provider_name == "defuddle"
        assert chain.providers[2].provider_name == "playwright"
        assert chain.providers[3].provider_name == "crawlee"
        assert chain.providers[4].provider_name == "direct_html"

    def test_scrapling_disabled_skipped(self):
        """When scrapling_enabled=False, the scrapling provider is skipped."""
        scraper_cfg = ScraperConfig(scrapling_enabled=False)
        cfg = make_test_app_config(scraper=scraper_cfg)

        with (
            patch("app.adapters.content.scraper.factory._build_scrapling") as mock_scrapling,
            patch("app.adapters.content.scraper.factory._build_playwright") as mock_playwright,
            patch("app.adapters.content.scraper.factory._build_crawlee") as mock_crawlee,
            patch("app.adapters.content.scraper.factory._build_direct_html") as mock_direct,
        ):
            mock_scrapling.return_value = None  # disabled
            mock_playwright.return_value = _MockProvider(name="playwright")
            mock_crawlee.return_value = _MockProvider(name="crawlee")
            mock_direct.return_value = _MockProvider(name="direct_html")

            chain = ContentScraperFactory.create_from_config(cfg)

        names = [p.provider_name for p in chain.providers]
        assert "scrapling" not in names
        assert "playwright" in names
        assert "crawlee" in names
        assert "direct_html" in names

    def test_playwright_disabled_skipped(self):
        """When playwright_enabled=False, the playwright provider is skipped."""
        scraper_cfg = ScraperConfig(playwright_enabled=False)
        cfg = make_test_app_config(scraper=scraper_cfg)

        with (
            patch("app.adapters.content.scraper.factory._build_scrapling") as mock_scrapling,
            patch("app.adapters.content.scraper.factory._build_playwright") as mock_playwright,
            patch("app.adapters.content.scraper.factory._build_crawlee") as mock_crawlee,
            patch("app.adapters.content.scraper.factory._build_direct_html") as mock_direct,
        ):
            mock_scrapling.return_value = _MockProvider(name="scrapling")
            mock_playwright.return_value = None
            mock_crawlee.return_value = _MockProvider(name="crawlee")
            mock_direct.return_value = _MockProvider(name="direct_html")

            chain = ContentScraperFactory.create_from_config(cfg)

        names = [p.provider_name for p in chain.providers]
        assert "playwright" not in names
        assert "crawlee" in names
        assert "direct_html" in names

    def test_crawlee_disabled_skipped(self):
        """When crawlee_enabled=False, the Crawlee provider is skipped."""
        scraper_cfg = ScraperConfig(crawlee_enabled=False)
        cfg = make_test_app_config(scraper=scraper_cfg)

        with (
            patch("app.adapters.content.scraper.factory._build_scrapling") as mock_scrapling,
            patch("app.adapters.content.scraper.factory._build_playwright") as mock_playwright,
            patch("app.adapters.content.scraper.factory._build_crawlee") as mock_crawlee,
            patch("app.adapters.content.scraper.factory._build_direct_html") as mock_direct,
        ):
            mock_scrapling.return_value = _MockProvider(name="scrapling")
            mock_playwright.return_value = _MockProvider(name="playwright")
            mock_crawlee.return_value = None
            mock_direct.return_value = _MockProvider(name="direct_html")

            chain = ContentScraperFactory.create_from_config(cfg)

        names = [p.provider_name for p in chain.providers]
        assert "crawlee" not in names
        assert "direct_html" in names

    def test_firecrawl_self_hosted_enabled_included(self):
        """When firecrawl_self_hosted_enabled=True, firecrawl is in the chain."""
        scraper_cfg = ScraperConfig(
            firecrawl_self_hosted_enabled=True,
            provider_order=["scrapling", "firecrawl", "playwright", "crawlee", "direct_html"],
        )
        cfg = make_test_app_config(scraper=scraper_cfg)

        mock_fc_provider = _MockProvider(name="firecrawl_self_hosted")

        with (
            patch("app.adapters.content.scraper.factory._build_scrapling") as mock_scrapling,
            patch("app.adapters.content.scraper.factory._build_firecrawl") as mock_firecrawl,
            patch("app.adapters.content.scraper.factory._build_playwright") as mock_playwright,
            patch("app.adapters.content.scraper.factory._build_crawlee") as mock_crawlee,
            patch("app.adapters.content.scraper.factory._build_direct_html") as mock_direct,
        ):
            mock_scrapling.return_value = _MockProvider(name="scrapling")
            mock_firecrawl.return_value = mock_fc_provider
            mock_playwright.return_value = _MockProvider(name="playwright")
            mock_crawlee.return_value = _MockProvider(name="crawlee")
            mock_direct.return_value = _MockProvider(name="direct_html")

            chain = ContentScraperFactory.create_from_config(cfg)

        names = [p.provider_name for p in chain.providers]
        assert "firecrawl_self_hosted" in names
        assert "playwright" in names
        assert "crawlee" in names
        assert len(chain.providers) == 5

    def test_empty_provider_order_falls_back_to_direct_html(self):
        """When provider_order is empty, the factory falls back to direct_html."""
        scraper_cfg = ScraperConfig(provider_order=[])
        cfg = make_test_app_config(scraper=scraper_cfg)

        chain = ContentScraperFactory.create_from_config(cfg)

        assert len(chain.providers) >= 1
        names = [p.provider_name for p in chain.providers]
        assert "direct_html" in names

    def test_browser_disabled_skips_playwright_and_crawlee(self):
        """When browser_enabled=False, browser providers are skipped regardless of order."""
        scraper_cfg = ScraperConfig(browser_enabled=False)
        cfg = make_test_app_config(scraper=scraper_cfg)

        with (
            patch("app.adapters.content.scraper.factory._build_scrapling") as mock_scrapling,
            patch("app.adapters.content.scraper.factory._build_firecrawl") as mock_firecrawl,
            patch("app.adapters.content.scraper.factory._build_playwright") as mock_playwright,
            patch("app.adapters.content.scraper.factory._build_crawlee") as mock_crawlee,
            patch("app.adapters.content.scraper.factory._build_direct_html") as mock_direct,
        ):
            mock_scrapling.return_value = _MockProvider(name="scrapling")
            mock_firecrawl.return_value = _MockProvider(name="firecrawl_self_hosted")
            mock_playwright.return_value = _MockProvider(name="playwright")
            mock_crawlee.return_value = _MockProvider(name="crawlee")
            mock_direct.return_value = _MockProvider(name="direct_html")
            chain = ContentScraperFactory.create_from_config(cfg)

        names = [p.provider_name for p in chain.providers]
        assert "playwright" not in names
        assert "crawlee" not in names
        assert "scrapling" in names
        assert "direct_html" in names
        mock_playwright.assert_not_called()
        mock_crawlee.assert_not_called()

    def test_force_provider_builds_single_provider(self):
        scraper_cfg = ScraperConfig(force_provider="direct_html")
        cfg = make_test_app_config(scraper=scraper_cfg)

        with (
            patch("app.adapters.content.scraper.factory._build_scrapling") as mock_scrapling,
            patch("app.adapters.content.scraper.factory._build_direct_html") as mock_direct,
        ):
            mock_scrapling.return_value = _MockProvider(name="scrapling")
            mock_direct.return_value = _MockProvider(name="direct_html")

            chain = ContentScraperFactory.create_from_config(cfg)

        assert len(chain.providers) == 1
        assert chain.providers[0].provider_name == "direct_html"
        mock_scrapling.assert_not_called()

    def test_force_provider_unavailable_raises_runtime_error(self):
        scraper_cfg = ScraperConfig(force_provider="playwright", browser_enabled=False)
        cfg = make_test_app_config(scraper=scraper_cfg)

        with pytest.raises(RuntimeError, match="SCRAPER_FORCE_PROVIDER='playwright'"):
            ContentScraperFactory.create_from_config(cfg)

    def test_scraper_disabled_returns_disabled_provider(self):
        scraper_cfg = ScraperConfig(enabled=False)
        cfg = make_test_app_config(scraper=scraper_cfg)

        chain = ContentScraperFactory.create_from_config(cfg)
        assert len(chain.providers) == 1
        assert chain.providers[0].provider_name == "scraper_disabled"

    def test_audit_callback_forwarded_to_chain(self):
        """The audit callback is passed through to the created chain."""
        scraper_cfg = ScraperConfig(provider_order=["direct_html"])
        cfg = make_test_app_config(scraper=scraper_cfg)
        audit = MagicMock()

        with patch("app.adapters.content.scraper.factory._build_direct_html") as mock_direct:
            mock_direct.return_value = _MockProvider(name="direct_html")
            chain = ContentScraperFactory.create_from_config(cfg, audit=audit)

        assert chain._audit is audit

    def test_defuddle_included_in_default_chain(self):
        """defuddle appears in chain when enabled (default)."""
        cfg = make_test_app_config()
        with (
            patch(
                "app.adapters.content.scraper.factory._build_scrapling",
                return_value=_MockProvider("scrapling"),
            ),
            patch(
                "app.adapters.content.scraper.factory._build_defuddle",
                return_value=_MockProvider("defuddle"),
            ),
            patch("app.adapters.content.scraper.factory._build_firecrawl", return_value=None),
            patch(
                "app.adapters.content.scraper.factory._build_playwright",
                return_value=_MockProvider("playwright"),
            ),
            patch(
                "app.adapters.content.scraper.factory._build_crawlee",
                return_value=_MockProvider("crawlee"),
            ),
            patch(
                "app.adapters.content.scraper.factory._build_direct_html",
                return_value=_MockProvider("direct_html"),
            ),
        ):
            chain = ContentScraperFactory.create_from_config(cfg)
        names = [p.provider_name for p in chain.providers]
        assert "defuddle" in names
        assert names.index("defuddle") > names.index("scrapling")

    def test_defuddle_disabled_absent_from_chain(self):
        """When _build_defuddle returns None, defuddle is absent."""
        cfg = make_test_app_config()
        with (
            patch(
                "app.adapters.content.scraper.factory._build_scrapling",
                return_value=_MockProvider("scrapling"),
            ),
            patch(
                "app.adapters.content.scraper.factory._build_defuddle",
                return_value=None,
            ),
            patch("app.adapters.content.scraper.factory._build_firecrawl", return_value=None),
            patch(
                "app.adapters.content.scraper.factory._build_playwright",
                return_value=_MockProvider("playwright"),
            ),
            patch(
                "app.adapters.content.scraper.factory._build_crawlee",
                return_value=_MockProvider("crawlee"),
            ),
            patch(
                "app.adapters.content.scraper.factory._build_direct_html",
                return_value=_MockProvider("direct_html"),
            ),
        ):
            chain = ContentScraperFactory.create_from_config(cfg)
        names = [p.provider_name for p in chain.providers]
        assert "defuddle" not in names


# ===================================================================
# FirecrawlProvider tests
# ===================================================================


class TestFirecrawlProvider:
    """Tests for the thin FirecrawlProvider wrapper."""

    @pytest.mark.asyncio(loop_scope="function")
    async def test_delegates_to_client_scrape_markdown(self):
        """scrape_markdown forwards the call to the underlying client."""
        mock_client = AsyncMock()
        long_content = "A " * 300  # 600 chars, above default min_content_length
        expected = _ok_result(markdown=long_content)
        mock_client.scrape_markdown.return_value = expected

        provider = FirecrawlProvider(mock_client, name="fc_test")
        result = await provider.scrape_markdown("https://example.com", mobile=False, request_id=7)

        assert result is expected
        mock_client.scrape_markdown.assert_awaited_once_with(
            "https://example.com",
            mobile=False,
            request_id=7,
            wait_for_ms_override=3000,
        )

    def test_provider_name_returns_configured_name(self):
        """provider_name returns the name passed at construction."""
        mock_client = AsyncMock()
        provider = FirecrawlProvider(mock_client, name="firecrawl_self_hosted")
        assert provider.provider_name == "firecrawl_self_hosted"

    def test_provider_name_default(self):
        """Default provider_name is 'firecrawl'."""
        mock_client = AsyncMock()
        provider = FirecrawlProvider(mock_client)
        assert provider.provider_name == "firecrawl"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_aclose_delegates_to_client(self):
        """aclose() calls the client's aclose()."""
        mock_client = AsyncMock()
        provider = FirecrawlProvider(mock_client, name="fc_test")
        await provider.aclose()
        mock_client.aclose.assert_awaited_once()


# ===================================================================
# CrawleeProvider tests
# ===================================================================


class TestScraplingProvider:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_custom_min_content_length_is_honored(self):
        from app.adapters.content.scraper.scrapling_provider import ScraplingProvider

        provider = ScraplingProvider(timeout_sec=5, min_content_length=10)
        with patch.object(
            provider,
            "_fetch",
            new_callable=AsyncMock,
            return_value=("<html><body>tiny</body></html>", "tiny"),
        ):
            result = await provider.scrape_markdown("https://example.com")

        assert result.status == "error"
        assert "insufficient content" in (result.error_text or "").lower()


class TestCrawleeProvider:
    """Tests for the Crawlee hybrid fallback provider."""

    @pytest.mark.asyncio(loop_scope="function")
    async def test_beautifulsoup_success_short_circuits_playwright_stage(self):
        """BeautifulSoup stage success should skip Playwright stage."""
        from app.adapters.content.scraper.crawlee_provider import CrawleeProvider

        provider = CrawleeProvider(timeout_sec=5, headless=True, max_retries=2)
        html_body = "<html><body><main>" + ("A" * 500) + "</main></body></html>"

        with (
            patch.object(
                provider,
                "_extract_with_beautifulsoup",
                new_callable=AsyncMock,
                return_value=html_body,
            ) as mock_bs,
            patch.object(provider, "_extract_with_playwright", new_callable=AsyncMock) as mock_pw,
            patch(
                "app.adapters.content.scraper.crawlee_provider.html_to_text",
                return_value="A" * 500,
            ),
        ):
            result = await provider.scrape_markdown("https://example.com")

        assert result.status == "ok"
        assert result.endpoint == "crawlee"
        assert isinstance(result.options_json, dict)
        assert result.options_json.get("stage") == "beautifulsoup"
        mock_bs.assert_awaited_once()
        mock_pw.assert_not_awaited()

    @pytest.mark.asyncio(loop_scope="function")
    async def test_beautifulsoup_thin_then_playwright_success(self):
        """If BeautifulSoup is thin, provider should fallback to Playwright stage."""
        from app.adapters.content.scraper.crawlee_provider import CrawleeProvider

        provider = CrawleeProvider(timeout_sec=5, headless=True, max_retries=2)
        bs_html = "<html><body><p>tiny</p></body></html>"
        pw_html = "<html><body><article>" + ("B" * 500) + "</article></body></html>"

        with (
            patch.object(
                provider,
                "_extract_with_beautifulsoup",
                new_callable=AsyncMock,
                return_value=bs_html,
            ) as mock_bs,
            patch.object(
                provider,
                "_extract_with_playwright",
                new_callable=AsyncMock,
                return_value=pw_html,
            ) as mock_pw,
            patch(
                "app.adapters.content.scraper.crawlee_provider.html_to_text",
                side_effect=lambda html: "tiny" if "tiny" in html else ("B" * 500),
            ),
        ):
            result = await provider.scrape_markdown("https://example.com", mobile=False)

        assert result.status == "ok"
        assert isinstance(result.options_json, dict)
        assert result.options_json.get("stage") == "playwright"
        mock_bs.assert_awaited_once()
        mock_pw.assert_awaited_once()

    @pytest.mark.asyncio(loop_scope="function")
    async def test_both_stages_fail_returns_error(self):
        """If both stages fail to produce content, provider returns error result."""
        from app.adapters.content.scraper.crawlee_provider import CrawleeProvider

        provider = CrawleeProvider(timeout_sec=5)

        with (
            patch.object(
                provider,
                "_extract_with_beautifulsoup",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(
                provider,
                "_extract_with_playwright",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await provider.scrape_markdown("https://example.com")

        assert result.status == "error"
        assert result.endpoint == "crawlee"
        assert "exhausted" in (result.error_text or "").lower()

    @pytest.mark.asyncio(loop_scope="function")
    async def test_timeout_path_returns_error(self):
        """Timeout in both stages should still return a graceful error result."""
        from app.adapters.content.scraper.crawlee_provider import CrawleeProvider

        provider = CrawleeProvider(timeout_sec=1)

        with (
            patch.object(
                provider,
                "_extract_with_beautifulsoup",
                new_callable=AsyncMock,
                side_effect=TimeoutError("bs timeout"),
            ),
            patch.object(
                provider,
                "_extract_with_playwright",
                new_callable=AsyncMock,
                side_effect=TimeoutError("pw timeout"),
            ),
        ):
            result = await provider.scrape_markdown("https://example.com")

        assert result.status == "error"
        assert result.endpoint == "crawlee"
        assert "timeout" in (result.error_text or "").lower()

    @pytest.mark.asyncio(loop_scope="function")
    async def test_custom_min_content_length_is_honored(self):
        from app.adapters.content.scraper.crawlee_provider import CrawleeProvider

        provider = CrawleeProvider(timeout_sec=5, min_content_length=10)
        html_body = "<html><body><article>1234567</article></body></html>"
        with (
            patch.object(
                provider,
                "_extract_with_beautifulsoup",
                new_callable=AsyncMock,
                return_value=html_body,
            ),
            patch.object(
                provider,
                "_extract_with_playwright",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.adapters.content.scraper.crawlee_provider.html_to_text",
                return_value="1234567",
            ),
        ):
            result = await provider.scrape_markdown("https://example.com")

        assert result.status == "error"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_aclose_is_noop(self):
        """aclose() completes without error (no persistent resources)."""
        from app.adapters.content.scraper.crawlee_provider import CrawleeProvider

        provider = CrawleeProvider()
        await provider.aclose()


# ===================================================================
# PlaywrightProvider tests
# ===================================================================


class TestPlaywrightProvider:
    """Tests for the Playwright browser-rendered fallback provider."""

    @pytest.mark.asyncio(loop_scope="function")
    async def test_successful_render_returns_ok(self):
        """A successful rendered fetch with enough content returns status='ok'."""
        from app.adapters.content.scraper.playwright_provider import PlaywrightProvider

        html_body = "<html><body><main>" + ("A" * 500) + "</main></body></html>"
        extracted_text = "A" * 500

        provider = PlaywrightProvider(timeout_sec=5, headless=True)

        with (
            patch.object(provider, "_render_html", new_callable=AsyncMock, return_value=html_body),
            patch(
                "app.adapters.content.scraper.playwright_provider.html_to_text",
                return_value=extracted_text,
            ),
        ):
            result = await provider.scrape_markdown("https://example.com", mobile=True)

        assert result.status == "ok"
        assert result.http_status == 200
        assert result.content_html == html_body
        assert result.endpoint == "playwright"
        assert result.options_json == {"provider": "playwright", "headless": True, "mobile": True}

    @pytest.mark.asyncio(loop_scope="function")
    async def test_timeout_returns_error(self):
        """When render times out, result is an error."""
        from app.adapters.content.scraper.playwright_provider import PlaywrightProvider

        provider = PlaywrightProvider(timeout_sec=1)

        with patch.object(
            provider,
            "_render_html",
            new_callable=AsyncMock,
            side_effect=TimeoutError("timed out"),
        ):
            result = await provider.scrape_markdown("https://example.com")

        assert result.status == "error"
        assert "timeout" in (result.error_text or "").lower()
        assert result.endpoint == "playwright"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_content_too_short_returns_error(self):
        """When extracted text is shorter than threshold, result is an error."""
        from app.adapters.content.scraper.playwright_provider import PlaywrightProvider

        provider = PlaywrightProvider(timeout_sec=5)
        short_html = "<html><body><p>tiny</p></body></html>"

        with (
            patch.object(provider, "_render_html", new_callable=AsyncMock, return_value=short_html),
            patch(
                "app.adapters.content.scraper.playwright_provider.html_to_text",
                return_value="tiny",
            ),
        ):
            result = await provider.scrape_markdown("https://example.com")

        assert result.status == "error"
        assert "too short" in (result.error_text or "").lower()
        assert result.endpoint == "playwright"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_custom_min_text_length_is_honored(self):
        from app.adapters.content.scraper.playwright_provider import PlaywrightProvider

        provider = PlaywrightProvider(timeout_sec=5, min_text_length=5)
        short_html = "<html><body><p>tiny</p></body></html>"

        with (
            patch.object(provider, "_render_html", new_callable=AsyncMock, return_value=short_html),
            patch(
                "app.adapters.content.scraper.playwright_provider.html_to_text",
                return_value="1234",
            ),
        ):
            result = await provider.scrape_markdown("https://example.com")

        assert result.status == "error"
        assert "too short" in (result.error_text or "").lower()

    @pytest.mark.asyncio(loop_scope="function")
    async def test_aclose_is_noop(self):
        """aclose() completes without error (no pooled resources)."""
        from app.adapters.content.scraper.playwright_provider import PlaywrightProvider

        provider = PlaywrightProvider()
        await provider.aclose()  # Should not raise


# ===================================================================
# DirectHTMLProvider tests
# ===================================================================


class TestDirectHTMLProvider:
    """Tests for the direct HTML fetch provider."""

    @pytest.mark.asyncio(loop_scope="function")
    async def test_successful_fetch_returns_ok(self):
        """A successful HTML fetch with enough content returns status='ok'."""
        from app.adapters.content.scraper.direct_html_provider import DirectHTMLProvider

        html_body = "<html><body><p>" + ("A" * 500) + "</p></body></html>"
        extracted_text = "A" * 500

        provider = DirectHTMLProvider(timeout_sec=5)

        with (
            patch.object(provider, "_fetch_html", new_callable=AsyncMock, return_value=html_body),
            patch(
                "app.adapters.content.scraper.direct_html_provider.html_to_text",
                return_value=extracted_text,
            ),
        ):
            result = await provider.scrape_markdown("https://example.com")

        assert result.status == "ok"
        assert result.http_status == 200
        assert result.content_html == html_body
        assert result.source_url == "https://example.com"
        assert result.endpoint == "direct_html"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_non_200_returns_none_html_and_error(self):
        """When _fetch_html returns None (non-200 or non-HTML), result is an error."""
        from app.adapters.content.scraper.direct_html_provider import DirectHTMLProvider

        provider = DirectHTMLProvider(timeout_sec=5)

        with patch.object(provider, "_fetch_html", new_callable=AsyncMock, return_value=None):
            result = await provider.scrape_markdown("https://example.com")

        assert result.status == "error"
        assert "no usable content" in result.error_text

    @pytest.mark.asyncio(loop_scope="function")
    async def test_content_too_short_returns_error(self):
        """When extracted text is shorter than the threshold, result is an error."""
        from app.adapters.content.scraper.direct_html_provider import DirectHTMLProvider

        short_html = "<html><body><p>Hi</p></body></html>"
        provider = DirectHTMLProvider(timeout_sec=5)

        with (
            patch.object(provider, "_fetch_html", new_callable=AsyncMock, return_value=short_html),
            patch(
                "app.adapters.content.scraper.direct_html_provider.html_to_text",
                return_value="Hi",
            ),
        ):
            result = await provider.scrape_markdown("https://example.com")

        assert result.status == "error"
        assert "too short" in result.error_text

    @pytest.mark.asyncio(loop_scope="function")
    async def test_custom_min_text_length_is_honored(self):
        from app.adapters.content.scraper.direct_html_provider import DirectHTMLProvider

        provider = DirectHTMLProvider(timeout_sec=5, min_text_length=10)
        html_body = "<html><body><p>12345</p></body></html>"

        with (
            patch.object(provider, "_fetch_html", new_callable=AsyncMock, return_value=html_body),
            patch(
                "app.adapters.content.scraper.direct_html_provider.html_to_text",
                return_value="12345",
            ),
        ):
            result = await provider.scrape_markdown("https://example.com")

        assert result.status == "error"
        assert "too short" in (result.error_text or "").lower()

    @pytest.mark.asyncio(loop_scope="function")
    async def test_timeout_returns_error(self):
        """When _fetch_html raises a timeout, the result is an error."""
        from app.adapters.content.scraper.direct_html_provider import DirectHTMLProvider

        provider = DirectHTMLProvider(timeout_sec=1)

        with patch.object(
            provider,
            "_fetch_html",
            new_callable=AsyncMock,
            side_effect=TimeoutError("timed out"),
        ):
            result = await provider.scrape_markdown("https://example.com")

        assert result.status == "error"
        assert "failed" in result.error_text.lower() or "timed out" in result.error_text.lower()
        assert result.source_url == "https://example.com"
        assert result.endpoint == "direct_html"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_httpx_connect_error_returns_error(self):
        """An httpx connection error is caught and returned as error result."""
        import httpx

        from app.adapters.content.scraper.direct_html_provider import DirectHTMLProvider

        provider = DirectHTMLProvider(timeout_sec=1)

        with patch.object(
            provider,
            "_fetch_html",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("connection refused"),
        ):
            result = await provider.scrape_markdown("https://example.com")

        assert result.status == "error"
        assert result.endpoint == "direct_html"

    def test_provider_name(self):
        """provider_name is 'direct_html'."""
        from app.adapters.content.scraper.direct_html_provider import DirectHTMLProvider

        provider = DirectHTMLProvider()
        assert provider.provider_name == "direct_html"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_aclose_is_noop(self):
        """aclose() completes without error (no resources to release)."""
        from app.adapters.content.scraper.direct_html_provider import DirectHTMLProvider

        provider = DirectHTMLProvider()
        await provider.aclose()  # Should not raise


# ===================================================================
# Chain-level min_content_length tests
# ===================================================================


class TestChainMinContentLength:
    """Tests for chain-level content length enforcement."""

    @pytest.mark.asyncio(loop_scope="function")
    async def test_chain_rejects_thin_content_and_falls_through(self):
        """Chain with min_content_length rejects short OK result, tries next provider."""
        thin = _ok_result(markdown="nav stub only")
        good = _ok_result(markdown="A " * 300)  # 600 chars

        p1 = _MockProvider(name="firecrawl", result=thin)
        p2 = _MockProvider(name="playwright", result=good)

        chain = ContentScraperChain([p1, p2], min_content_length=400)
        result = await chain.scrape_markdown("https://example.com")

        assert result.status == "ok"
        assert result.content_markdown == good.content_markdown
        assert len(p1.calls) == 1
        assert len(p2.calls) == 1

    @pytest.mark.asyncio(loop_scope="function")
    async def test_chain_accepts_sufficient_content(self):
        """Chain with min_content_length accepts result meeting threshold."""
        good = _ok_result(markdown="A " * 300)

        p1 = _MockProvider(name="firecrawl", result=good)
        p2 = _MockProvider(name="playwright", result=_ok_result())

        chain = ContentScraperChain([p1, p2], min_content_length=400)
        result = await chain.scrape_markdown("https://example.com")

        assert result.status == "ok"
        assert result.content_markdown == good.content_markdown
        assert len(p2.calls) == 0  # Not reached

    @pytest.mark.asyncio(loop_scope="function")
    async def test_chain_default_zero_accepts_any_content(self):
        """Chain with default min_content_length=0 accepts any non-empty content."""
        short = _ok_result(markdown="# OK")

        p1 = _MockProvider(name="first", result=short)
        chain = ContentScraperChain([p1])  # default min_content_length=0
        result = await chain.scrape_markdown("https://example.com")

        assert result.status == "ok"
        assert result.content_markdown == "# OK"


# ---------------------------------------------------------------------------
# JS-heavy host reordering
# ---------------------------------------------------------------------------


class TestJsHeavyReordering:
    """Chain should try browser providers first for JS-heavy hosts."""

    @pytest.mark.asyncio
    async def test_chain_reorders_for_js_heavy_url(self) -> None:
        scrapling = _MockProvider(name="scrapling", result=_ok_result())
        playwright = _MockProvider(name="playwright", result=_ok_result())

        chain = ContentScraperChain(
            [scrapling, playwright],
            js_heavy_hosts=("techradar.com",),
        )
        result = await chain.scrape_markdown("https://www.techradar.com/article")

        assert result.status == CallStatus.OK
        assert len(playwright.calls) == 1
        assert len(scrapling.calls) == 0  # never reached

    @pytest.mark.asyncio
    async def test_chain_keeps_order_for_normal_url(self) -> None:
        scrapling = _MockProvider(name="scrapling", result=_ok_result())
        playwright = _MockProvider(name="playwright", result=_ok_result())

        chain = ContentScraperChain(
            [scrapling, playwright],
            js_heavy_hosts=("techradar.com",),
        )
        result = await chain.scrape_markdown("https://example.com/article")

        assert result.status == CallStatus.OK
        assert len(scrapling.calls) == 1
        assert len(playwright.calls) == 0  # not reached, scrapling succeeded
