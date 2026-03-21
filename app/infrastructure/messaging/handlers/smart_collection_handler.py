"""EventBus handler: auto-populate smart collections when summaries are created."""

from __future__ import annotations

from typing import TYPE_CHECKING

import peewee

from app.core.logging_utils import get_logger
from app.db.models import (
    Collection,
    CollectionItem,
    Request,
    Summary,
    SummaryTag,
    Tag,
    model_to_dict,
)
from app.domain.services.smart_collection import evaluate_summary
from app.domain.services.summary_context import build_summary_context

if TYPE_CHECKING:
    from app.domain.events.summary_events import SummaryCreated

logger = get_logger(__name__)


class SmartCollectionHandler:
    """On SummaryCreated, evaluate against all user's smart collections."""

    async def on_summary_created(self, event: SummaryCreated) -> None:
        try:
            # 1. Resolve user_id from Request table
            request = Request.get_by_id(event.request_id)
            user_id = request.user_id
            if not user_id:
                return

            # 2. Load all smart collections for this user
            smart_collections = list(
                Collection.select().where(
                    (Collection.user == user_id)
                    & (Collection.collection_type == "smart")
                    & (Collection.is_deleted == False)  # noqa: E712
                )
            )
            if not smart_collections:
                return

            # 3. Build context from the new summary
            summary = Summary.get_by_id(event.summary_id)
            summary_dict = model_to_dict(summary)
            request_dict = model_to_dict(request)

            tag_names = [
                st.tag.name
                for st in SummaryTag.select(SummaryTag, Tag)
                .join(Tag)
                .where(SummaryTag.summary == event.summary_id)
            ]

            context = build_summary_context(summary_dict, request_dict, tag_names)

            # 4. Evaluate against each smart collection
            added_count = 0
            for coll in smart_collections:
                conditions = coll.query_conditions_json or []
                match_mode = coll.query_match_mode or "all"

                if not conditions:
                    continue

                if evaluate_summary(conditions, context, match_mode):
                    # Check if already in collection (avoid duplicates)
                    exists = (
                        CollectionItem.select()
                        .where(
                            (CollectionItem.collection == coll.id)
                            & (CollectionItem.summary == event.summary_id)
                        )
                        .exists()
                    )

                    if not exists:
                        max_pos = (
                            CollectionItem.select(peewee.fn.MAX(CollectionItem.position))
                            .where(CollectionItem.collection == coll.id)
                            .scalar()
                            or 0
                        )

                        CollectionItem.create(
                            collection=coll.id,
                            summary=event.summary_id,
                            position=max_pos + 1,
                        )
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
