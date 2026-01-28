import unittest

from app.core.url_utils import extract_all_urls, looks_like_url, normalize_url, url_hash_sha256


class TestURLUtils(unittest.TestCase):
    def test_normalize_url_removes_tracking_and_sorts(self):
        url = "HTTPS://Example.COM/Path/?b=2&utm_source=x&a=1#frag"
        norm = normalize_url(url)
        assert norm == "https://example.com/Path?a=1&b=2"

    def test_normalize_url_trailing_slash(self):
        assert normalize_url("http://example.com/") == "http://example.com/"
        assert normalize_url("http://example.com/path/") == "http://example.com/path"

    def test_normalize_url_handles_missing_scheme_and_tracking(self):
        assert normalize_url("example.com") == "http://example.com/"
        url = "EXAMPLE.com/Path?A=1&UTM_Source=x"
        assert normalize_url(url) == "http://example.com/Path?A=1"

    def test_url_hash(self):
        norm = normalize_url("http://example.com/path?a=1")
        h = url_hash_sha256(norm)
        assert len(h) == 64

    def test_looks_like_url(self):
        assert looks_like_url("see https://example.org/ok?x=1")
        assert not looks_like_url("no url here")

    def test_looks_like_url_with_www_prefix(self):
        """Test URL detection for www. URLs without protocol."""
        # URLs with www. prefix but no protocol should be detected
        assert looks_like_url("www.example.com")
        assert looks_like_url("www.darioamodei.com/essay/the-adolescence-of-technology")
        assert looks_like_url("check out www.example.org/path for more")
        # Still works with protocol
        assert looks_like_url("https://www.example.com")
        # No URL
        assert not looks_like_url("just some text")

    def test_extract_all_urls_with_www_prefix(self):
        """Test URL extraction for www. URLs without protocol."""
        # www. URL gets normalized with https://
        urls = extract_all_urls("www.example.com/path")
        assert urls == ["https://www.example.com/path"]

        # Mixed URLs with and without protocol
        urls = extract_all_urls("Visit www.foo.org and https://bar.com")
        assert "https://bar.com" in urls
        assert "https://www.foo.org" in urls

        # Deduplication: same URL with and without protocol
        urls = extract_all_urls("https://www.example.com and www.example.com")
        # Should have https:// version (found first) and not duplicate
        assert len([u for u in urls if "example.com" in u]) == 1


if __name__ == "__main__":
    unittest.main()
