"""Shared MCP test fixtures.

Provides an async helper for inserting a scoped summary with a fixed
created_at/updated_at timestamp, used by the MCP semantic-search tests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import update

from app.db.models import Summary
from tests.db_helpers_async import create_request, insert_summary

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession


async def insert_scoped_summary(
    session: AsyncSession,
    *,
    user_id: int,
    url: str,
    title: str,
    tags: list[str],
    created_at: datetime,
) -> tuple[int, int]:
    """Insert a request + summary scoped to user_id with deterministic timestamps."""
    request_id = await create_request(
        session,
        type_="url",
        status="completed",
        correlation_id=f"cid-{user_id}-{url}",
        chat_id=1,
        user_id=user_id,
        input_url=url,
        normalized_url=url,
    )
    summary_id = await insert_summary(
        session,
        request_id=request_id,
        lang="en",
        json_payload={
            "summary_250": f"Summary for {title}",
            "tldr": f"TLDR {title}",
            "topic_tags": tags,
            "metadata": {"title": title, "domain": "example.com"},
        },
    )
    await session.execute(
        update(Summary)
        .where(Summary.id == summary_id)
        .values(created_at=created_at, updated_at=created_at)
    )
    return summary_id, request_id
