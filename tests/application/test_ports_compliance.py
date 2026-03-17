"""Port compliance tests: verify factories return protocol-compliant adapters.

These tests assert that each repository factory in app/di/repositories.py
returns a concrete adapter that is recognised as an instance of its port
protocol (via @runtime_checkable isinstance checks) and that critical async
methods exist with the expected signatures.
"""

from __future__ import annotations

import inspect

import pytest

from app.application.ports import (
    LLMRepositoryPort,
    RequestRepositoryPort,
    SummaryRepositoryPort,
)
from tests.integration.helpers import temp_db


@pytest.fixture
def db():
    with temp_db() as session:
        yield session


def test_summary_repository_factory_returns_port_instance(db) -> None:
    from app.di.repositories import build_summary_repository

    repo = build_summary_repository(db)
    assert isinstance(repo, SummaryRepositoryPort)


def test_request_repository_factory_returns_port_instance(db) -> None:
    from app.di.repositories import build_request_repository

    repo = build_request_repository(db)
    assert isinstance(repo, RequestRepositoryPort)


def test_llm_repository_factory_returns_port_instance(db) -> None:
    from app.di.repositories import build_llm_repository

    repo = build_llm_repository(db)
    assert isinstance(repo, LLMRepositoryPort)


def test_summary_repository_critical_methods_are_async(db) -> None:
    from app.di.repositories import build_summary_repository

    repo = build_summary_repository(db)
    for method_name in ("async_get_user_summaries", "async_get_summary_context_by_id"):
        method = getattr(repo, method_name, None)
        assert method is not None, f"Missing method: {method_name}"
        assert inspect.iscoroutinefunction(method), f"{method_name} must be async"


def test_request_repository_critical_methods_are_async(db) -> None:
    from app.di.repositories import build_request_repository

    repo = build_request_repository(db)
    for method_name in ("async_create_request", "async_get_request_context"):
        method = getattr(repo, method_name, None)
        assert method is not None, f"Missing method: {method_name}"
        assert inspect.iscoroutinefunction(method), f"{method_name} must be async"
