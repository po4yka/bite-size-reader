"""Tests for app/infrastructure/cache/query_cache.py."""

from __future__ import annotations

from app.infrastructure.cache.query_cache import RedisQueryCache


def test_make_hash_is_deterministic() -> None:
    h1 = RedisQueryCache._make_hash("get_user", 42, key="val")
    h2 = RedisQueryCache._make_hash("get_user", 42, key="val")
    assert h1 == h2


def test_make_hash_differs_by_query_name() -> None:
    h1 = RedisQueryCache._make_hash("get_user", 1)
    h2 = RedisQueryCache._make_hash("get_items", 1)
    assert h1 != h2


def test_make_hash_differs_by_args() -> None:
    h1 = RedisQueryCache._make_hash("get_user", 1)
    h2 = RedisQueryCache._make_hash("get_user", 2)
    assert h1 != h2


def test_make_hash_differs_by_kwargs() -> None:
    h1 = RedisQueryCache._make_hash("query", foo="a")
    h2 = RedisQueryCache._make_hash("query", foo="b")
    assert h1 != h2


def test_make_hash_length() -> None:
    h = RedisQueryCache._make_hash("any_query")
    assert len(h) == 32


def test_make_hash_no_args() -> None:
    h = RedisQueryCache._make_hash("simple_query")
    assert isinstance(h, str)
    assert len(h) == 32


def test_make_hash_kwargs_order_independent() -> None:
    h1 = RedisQueryCache._make_hash("q", a=1, b=2)
    h2 = RedisQueryCache._make_hash("q", b=2, a=1)
    assert h1 == h2
