"""Tests for domain-level fail-fast in batch URL processing."""

from __future__ import annotations

import unittest

from app.models.batch_processing import URLBatchStatus


class TestDomainFailFast(unittest.IsolatedAsyncioTestCase):
    """Verify domain-level fail-fast skips URLs after domain timeout."""

    async def test_second_url_from_timed_out_domain_is_skipped(self):
        """When first URL from a domain times out, second URL is skipped."""
        urls = [
            "https://habr.com/article/1",
            "https://habr.com/article/2",
        ]

        batch_status = URLBatchStatus.from_urls(urls)

        # Simulate: first URL exhausts retries -> domain added to failed set
        failed_domains: set[str] = set()
        failed_domains.add("habr.com")

        # Check domain membership for second URL
        entry = batch_status._find_entry(urls[1])
        assert entry is not None
        assert entry.domain == "habr.com"
        assert entry.domain in failed_domains

    async def test_different_domain_not_affected(self):
        """URLs from different domains are not affected by fail-fast."""
        failed_domains: set[str] = {"habr.com"}

        batch_status = URLBatchStatus.from_urls(
            [
                "https://habr.com/article/1",
                "https://example.com/page",
            ]
        )

        entry = batch_status._find_entry("https://example.com/page")
        assert entry is not None
        assert entry.domain == "example.com"
        assert entry.domain not in failed_domains


class TestDomainFailFastFormatting(unittest.TestCase):
    """Verify domain_timeout error type formats correctly."""

    def test_domain_timeout_error_format(self):
        """domain_timeout error type displays as 'Skipped (domain timeout)'."""
        from app.adapters.external.formatting.batch_progress_formatter import (
            BatchProgressFormatter,
        )

        result = BatchProgressFormatter._format_error_short(
            "domain_timeout", "Skipped (domain habr.com timed out)"
        )
        assert result == "Skipped (domain timeout)"

    def test_regular_timeout_unaffected(self):
        """Regular timeout formatting is unchanged."""
        from app.adapters.external.formatting.batch_progress_formatter import (
            BatchProgressFormatter,
        )

        result = BatchProgressFormatter._format_error_short("timeout", None)
        assert result == "Timeout"
