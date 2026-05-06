from __future__ import annotations

from typing import TYPE_CHECKING

from app.cli._legacy_peewee_models import Summary
from tests.db_helpers import create_request, insert_summary

if TYPE_CHECKING:
    from datetime import datetime

    from app.db.session import DatabaseSessionManager


def insert_scoped_summary(
    *,
    db: DatabaseSessionManager,
    user_id: int,
    url: str,
    title: str,
    tags: list[str],
    created_at: datetime,
) -> tuple[int, int]:
    request_id = create_request(
        type_="url",
        status="completed",
        correlation_id=f"cid-{user_id}-{url}",
        chat_id=1,
        user_id=user_id,
        input_url=url,
        normalized_url=url,
    )
    summary_id = insert_summary(
        request_id=request_id,
        lang="en",
        json_payload={
            "summary_250": f"Summary for {title}",
            "tldr": f"TLDR {title}",
            "topic_tags": tags,
            "metadata": {"title": title, "domain": "example.com"},
        },
    )
    Summary.update(
        {
            Summary.created_at: created_at,
            Summary.updated_at: created_at,
        }
    ).where(Summary.id == summary_id).execute()
    return summary_id, request_id
