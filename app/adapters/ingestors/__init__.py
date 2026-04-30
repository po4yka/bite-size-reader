"""Pluggable proactive source ingestors."""

from app.adapters.ingestors.hn import HackerNewsIngester
from app.adapters.ingestors.reddit import RedditIngester
from app.adapters.ingestors.runner import SourceIngestionRunner
from app.adapters.ingestors.twitter import TwitterIngester, TwitterIngestionConfig

__all__ = [
    "HackerNewsIngester",
    "RedditIngester",
    "SourceIngestionRunner",
    "TwitterIngester",
    "TwitterIngestionConfig",
]
