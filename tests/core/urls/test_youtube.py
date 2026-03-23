from __future__ import annotations

import pytest

from app.core.urls.youtube import extract_youtube_video_id, is_youtube_url


@pytest.mark.parametrize(
    ("url", "video_id"),
    [
        ("https://youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/watch?feature=share&v=abcdefghijk", "abcdefghijk"),
        ("https://youtu.be/12345678901", "12345678901"),
        ("https://youtube.com/embed/ZYXWVUTSRQP", "ZYXWVUTSRQP"),
        ("https://youtube.com/shorts/a1b2c3d4e5F", "a1b2c3d4e5F"),
    ],
)
def test_youtube_helpers_support_known_formats(url: str, video_id: str) -> None:
    assert is_youtube_url(url) is True
    assert extract_youtube_video_id(url) == video_id


def test_youtube_helpers_reject_lookalike_domains() -> None:
    url = "https://youtube-fake.com/watch?v=dQw4w9WgXcQ"

    assert is_youtube_url(url) is False
    assert extract_youtube_video_id(url) is None
