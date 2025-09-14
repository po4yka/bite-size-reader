import unittest

from app.core.url_utils import looks_like_url, normalize_url, url_hash_sha256


class TestURLUtils(unittest.TestCase):
    def test_normalize_url_removes_tracking_and_sorts(self):
        url = "HTTPS://Example.COM/Path/?b=2&utm_source=x&a=1#frag"
        norm = normalize_url(url)
        self.assertEqual(norm, "https://example.com/Path?a=1&b=2")

    def test_normalize_url_trailing_slash(self):
        self.assertEqual(normalize_url("http://example.com/"), "http://example.com/")
        self.assertEqual(normalize_url("http://example.com/path/"), "http://example.com/path")

    def test_url_hash(self):
        norm = normalize_url("http://example.com/path?a=1")
        h = url_hash_sha256(norm)
        self.assertEqual(len(h), 64)

    def test_looks_like_url(self):
        self.assertTrue(looks_like_url("see https://example.org/ok?x=1"))
        self.assertFalse(looks_like_url("no url here"))


if __name__ == "__main__":
    unittest.main()
