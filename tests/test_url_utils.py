import unittest

from app.core.url_utils import looks_like_url, normalize_url, url_hash_sha256


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


if __name__ == "__main__":
    unittest.main()
