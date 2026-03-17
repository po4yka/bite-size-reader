"""Tests for app/db/query_profiler.py."""

from __future__ import annotations

import pytest

from app.db.query_profiler import (
    AsyncQueryProfiler,
    QueryProfiler,
    _extract_operation_name,
    profile_query,
)


def test_extract_operation_name_select_prefixes() -> None:
    assert _extract_operation_name("get_user") == "select"
    assert _extract_operation_name("fetch_items") == "select"
    assert _extract_operation_name("find_by_id") == "select"
    assert _extract_operation_name("list_all") == "select"
    assert _extract_operation_name("search_articles") == "select"


def test_extract_operation_name_insert_prefixes() -> None:
    assert _extract_operation_name("insert_row") == "insert"
    assert _extract_operation_name("create_request") == "insert"
    assert _extract_operation_name("add_entry") == "insert"


def test_extract_operation_name_update_prefixes() -> None:
    assert _extract_operation_name("update_status") == "update"
    assert _extract_operation_name("modify_record") == "update"
    assert _extract_operation_name("set_flag") == "update"


def test_extract_operation_name_delete_prefixes() -> None:
    assert _extract_operation_name("delete_item") == "delete"
    assert _extract_operation_name("remove_entry") == "delete"


def test_extract_operation_name_unknown_returns_query() -> None:
    assert _extract_operation_name("execute_query") == "query"
    assert _extract_operation_name("do_something") == "query"
    assert _extract_operation_name("run") == "query"


def test_query_profiler_records_elapsed_time() -> None:
    with QueryProfiler("test_op", auto_log=False) as profiler:
        pass
    assert profiler.elapsed_ms >= 0.0


def test_query_profiler_elapsed_increases_with_work() -> None:
    import time

    with QueryProfiler("test_op", auto_log=False) as profiler:
        time.sleep(0.01)
    assert profiler.elapsed_ms >= 5.0  # at least 5ms


@pytest.mark.asyncio
async def test_async_query_profiler_records_elapsed_time() -> None:
    async with AsyncQueryProfiler("async_op", auto_log=False) as profiler:
        pass
    assert profiler.elapsed_ms >= 0.0


def test_profile_query_decorator_sync() -> None:
    calls = []

    @profile_query(threshold_ms=99999)
    def my_func(x: int) -> int:
        calls.append(x)
        return x * 2

    result = my_func(5)
    assert result == 10
    assert calls == [5]


@pytest.mark.asyncio
async def test_profile_query_decorator_async() -> None:
    calls = []

    @profile_query(threshold_ms=99999)
    async def my_async_func(x: int) -> int:
        calls.append(x)
        return x + 1

    result = await my_async_func(3)
    assert result == 4
    assert calls == [3]
