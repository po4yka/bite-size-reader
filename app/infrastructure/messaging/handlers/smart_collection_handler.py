"""EventBus handler: auto-populate smart collections when summaries are created."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.core.logging_utils import get_logger
from app.db.models import Collection, CollectionItem, Request, Summary, SummaryTag, Tag, model_to_dict
from app.domain.services.smart_collection import evaluate_summary
from app.domain.services.summary_context import build_summary_context

if TYPE_CHECKING:
    from app.db.session import Database
    from app.domain.events.summary_events import SummaryCreated

logger = get_logger(__name__)


class SmartCollectionHandler:
    """On SummaryCreated, evaluate against all user's smart collections."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def on_summary_created(self, event: SummaryCreated) -> None:
        try:
            async with self._database.transaction() as session:
                request = await session.get(Request, event.request_id)
                if request is None or not request.user_id:
                    return
                user_id = request.user_id

                smart_collections = list(
                    await session.scalars(
                        select(Collection).where(
                            Collection.user_id == user_id,
                            Collection.collection_type == "smart",
                            Collection.is_deleted.is_(False),
                        )
                    )
                )
                if not smart_collections:
                    return

                summary = await session.get(Summary, event.summary_id)
                if summary is None:
                    return

                tag_names = list(
                    await session.scalars(
                        select(Tag.name)
                        .join(SummaryTag, SummaryTag.tag_id == Tag.id)
                        .where(SummaryTag.summary_id == event.summary_id)
                    )
                )
                context = build_summary_context(
                    model_to_dict(summary),
                    model_to_dict(request),
                    tag_names,
                )

                added_count = 0
                for collection in smart_collections:
                    raw_conditions = collection.query_conditions_json
                    conditions = raw_conditions if isinstance(raw_conditions, list) else []
                    match_mode = collection.query_match_mode or "all"
                    if not conditions or not evaluate_summary(conditions, context, match_mode):
                        continue

                    max_position = int(
                        await session.scalar(
                            select(func.max(CollectionItem.position)).where(
                                CollectionItem.collection_id == collection.id
                            )
                        )
                        or 0
                    )
                    inserted_id = await session.scalar(
                        insert(CollectionItem)
                        .values(
                            collection_id=collection.id,
                            summary_id=event.summary_id,
                            position=max_position + 1,
                        )
                        .on_conflict_do_nothing(
                            index_elements=[
                                CollectionItem.collection_id,
                                CollectionItem.summary_id,
                            ]
                        )
                        .returning(CollectionItem.id)
                    )
                    if inserted_id is not None:
                        added_count += 1

            if added_count > 0:
                logger.info(
                    "smart_collections_auto_populated",
                    extra={
                        "user_id": user_id,
                        "summary_id": event.summary_id,
                        "collections_matched": added_count,
                    },
                )
        except Exception:
            logger.exception(
                "smart_collection_handler_error",
                extra={"summary_id": getattr(event, "summary_id", None)},
            )
