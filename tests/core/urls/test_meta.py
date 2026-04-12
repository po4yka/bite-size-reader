from __future__ import annotations

from app.core.urls.meta import (
    extract_instagram_shortcode,
    extract_threads_post_id,
    is_instagram_post_url,
    is_instagram_reel_url,
    is_instagram_url,
    is_threads_url,
)


def test_threads_url_detection_and_id_extraction() -> None:
    url = "https://www.threads.net/@user/post/C8abc123/?igshid=abc"

    assert is_threads_url(url) is True
    assert extract_threads_post_id(url) == "C8abc123"


def test_instagram_url_detection_and_shortcode_extraction() -> None:
    post_url = "https://www.instagram.com/p/DApost123/?utm_source=ig_web_copy_link"
    reel_url = "https://www.instagram.com/reel/DAreel456/?utm_source=ig_web_copy_link"

    assert is_instagram_url(post_url) is True
    assert is_instagram_post_url(post_url) is True
    assert is_instagram_reel_url(post_url) is False
    assert extract_instagram_shortcode(post_url) == "DApost123"

    assert is_instagram_url(reel_url) is True
    assert is_instagram_reel_url(reel_url) is True
    assert is_instagram_post_url(reel_url) is False
    assert extract_instagram_shortcode(reel_url) == "DAreel456"


def test_meta_detectors_reject_non_meta_urls() -> None:
    url = "https://example.com/article"

    assert is_threads_url(url) is False
    assert is_instagram_url(url) is False
    assert extract_threads_post_id(url) is None
    assert extract_instagram_shortcode(url) is None
