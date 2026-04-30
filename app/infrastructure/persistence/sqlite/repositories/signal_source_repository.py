"""SQLite repository for Phase 3 signal-source entities."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import peewee

from app.core.time_utils import UTC
from app.db.models import FeedItem, Source, Subscription, Topic, UserSignal, model_to_dict
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository


class SqliteSignalSourceRepositoryAdapter(SqliteBaseRepository):
    """Persistence adapter for sources, subscriptions, topics, and signals."""

    async def async_upsert_source(
        self,
        *,
        kind: str,
        external_id: str | None = None,
        url: str | None = None,
        title: str | None = None,
        description: str | None = None,
        site_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        def _upsert() -> dict[str, Any]:
            source, _created = Source.get_or_create(
                kind=kind,
                external_id=external_id,
                defaults={
                    "url": url,
                    "title": title,
                    "description": description,
                    "site_url": site_url,
                    "metadata_json": metadata,
                },
            )
            Source.update(
                {
                    Source.url: url,
                    Source.title: title,
                    Source.description: description,
                    Source.site_url: site_url,
                    Source.metadata_json: metadata,
                    Source.updated_at: datetime.now(UTC),
                }
            ).where(Source.id == source.id).execute()
            source = Source.get_by_id(source.id)
            data = model_to_dict(source)
            assert data is not None
            return data

        return await self._execute_transaction(_upsert, operation_name="upsert_signal_source")

    async def async_subscribe(
        self,
        *,
        user_id: int,
        source_id: int,
        topic_constraints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        def _upsert() -> dict[str, Any]:
            subscription, created = Subscription.get_or_create(
                user=user_id,
                source=source_id,
                defaults={"topic_constraints_json": topic_constraints, "is_active": True},
            )
            if not created:
                subscription.is_active = True
                subscription.topic_constraints_json = topic_constraints
                subscription.save()
            data = model_to_dict(subscription)
            assert data is not None
            return data

        return await self._execute_transaction(_upsert, operation_name="subscribe_signal_source")

    async def async_get_source(self, source_id: int) -> dict[str, Any] | None:
        def _query() -> dict[str, Any] | None:
            return model_to_dict(Source.get_or_none(Source.id == source_id))

        return await self._execute(_query, operation_name="get_signal_source", read_only=True)

    async def async_set_source_active(self, source_id: int, *, is_active: bool) -> bool:
        def _update() -> bool:
            return (
                Source.update(
                    {
                        Source.is_active: is_active,
                        Source.updated_at: datetime.now(UTC),
                    }
                )
                .where(Source.id == source_id)
                .execute()
                > 0
            )

        return await self._execute(_update, operation_name="set_signal_source_active")

    async def async_set_subscription_active(
        self,
        *,
        user_id: int,
        subscription_id: int,
        is_active: bool,
    ) -> bool:
        def _update() -> bool:
            return (
                Subscription.update(
                    {
                        Subscription.is_active: is_active,
                        Subscription.updated_at: datetime.now(UTC),
                    }
                )
                .where((Subscription.id == subscription_id) & (Subscription.user == user_id))
                .execute()
                > 0
            )

        return await self._execute(_update, operation_name="set_signal_subscription_active")

    async def async_upsert_feed_item(
        self,
        *,
        source_id: int,
        external_id: str,
        canonical_url: str | None = None,
        title: str | None = None,
        content_text: str | None = None,
        author: str | None = None,
        published_at: Any | None = None,
        engagement: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        engagement = engagement or {}

        def _upsert() -> dict[str, Any]:
            item, _created = FeedItem.get_or_create(
                source=source_id,
                external_id=external_id,
                defaults={
                    "canonical_url": canonical_url,
                    "title": title,
                    "content_text": content_text,
                    "author": author,
                    "published_at": published_at,
                    "views": engagement.get("views"),
                    "forwards": engagement.get("forwards"),
                    "comments": engagement.get("comments"),
                    "engagement_score": engagement.get("score"),
                    "metadata_json": metadata,
                },
            )
            FeedItem.update(
                {
                    FeedItem.canonical_url: canonical_url,
                    FeedItem.title: title,
                    FeedItem.content_text: content_text,
                    FeedItem.author: author,
                    FeedItem.published_at: published_at,
                    FeedItem.views: engagement.get("views"),
                    FeedItem.forwards: engagement.get("forwards"),
                    FeedItem.comments: engagement.get("comments"),
                    FeedItem.engagement_score: engagement.get("score"),
                    FeedItem.metadata_json: metadata,
                    FeedItem.updated_at: datetime.now(UTC),
                }
            ).where(FeedItem.id == item.id).execute()
            item = FeedItem.get_by_id(item.id)
            data = model_to_dict(item)
            assert data is not None
            return data

        return await self._execute_transaction(_upsert, operation_name="upsert_signal_feed_item")

    async def async_upsert_topic(
        self,
        *,
        user_id: int,
        name: str,
        description: str | None = None,
        weight: float = 1.0,
        embedding_ref: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        def _upsert() -> dict[str, Any]:
            topic, created = Topic.get_or_create(
                user=user_id,
                name=name,
                defaults={
                    "description": description,
                    "weight": weight,
                    "embedding_ref": embedding_ref,
                    "metadata_json": metadata,
                },
            )
            if not created:
                topic.description = description
                topic.weight = weight
                topic.embedding_ref = embedding_ref
                topic.metadata_json = metadata
                topic.is_active = True
                topic.save()
            data = model_to_dict(topic)
            assert data is not None
            return data

        return await self._execute_transaction(_upsert, operation_name="upsert_signal_topic")

    async def async_record_user_signal(
        self,
        *,
        user_id: int,
        feed_item_id: int,
        topic_id: int | None = None,
        status: str = "candidate",
        heuristic_score: float | None = None,
        llm_score: float | None = None,
        final_score: float | None = None,
        evidence: dict[str, Any] | None = None,
        filter_stage: str = "heuristic",
        llm_judge: dict[str, Any] | None = None,
        llm_cost_usd: float | None = None,
    ) -> dict[str, Any]:
        def _upsert() -> dict[str, Any]:
            signal, created = UserSignal.get_or_create(
                user=user_id,
                feed_item=feed_item_id,
                defaults={
                    "topic": topic_id,
                    "status": status,
                    "heuristic_score": heuristic_score,
                    "llm_score": llm_score,
                    "final_score": final_score,
                    "evidence_json": evidence,
                    "filter_stage": filter_stage,
                    "llm_judge_json": llm_judge,
                    "llm_cost_usd": llm_cost_usd,
                },
            )
            if not created:
                signal.topic = topic_id
                signal.status = status
                signal.heuristic_score = heuristic_score
                signal.llm_score = llm_score
                signal.final_score = final_score
                signal.evidence_json = evidence
                signal.filter_stage = filter_stage
                signal.llm_judge_json = llm_judge
                signal.llm_cost_usd = llm_cost_usd
                signal.save()
            data = model_to_dict(signal)
            assert data is not None
            return data

        return await self._execute_transaction(_upsert, operation_name="record_user_signal")

    async def async_list_user_subscriptions(self, user_id: int) -> list[dict[str, Any]]:
        def _query() -> list[dict[str, Any]]:
            rows = (
                Subscription.select(Subscription, Source)
                .join(Source)
                .where(Subscription.user == user_id)
                .order_by(Subscription.created_at.desc())
            )
            result: list[dict[str, Any]] = []
            for row in rows:
                data = model_to_dict(row) or {}
                data["source_kind"] = row.source.kind
                data["source_title"] = row.source.title
                data["source_url"] = row.source.url
                data["source_external_id"] = row.source.external_id
                result.append(data)
            return result

        return await self._execute(
            _query,
            operation_name="list_signal_subscriptions",
            read_only=True,
        )

    async def async_list_user_signals(
        self,
        user_id: int,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        def _query() -> list[dict[str, Any]]:
            query = (
                UserSignal.select(UserSignal, FeedItem, Topic, Source)
                .join(FeedItem)
                .join(Source)
                .switch(UserSignal)
                .join(Topic, peewee.JOIN.LEFT_OUTER)
                .where(UserSignal.user == user_id)
                .order_by(UserSignal.final_score.desc(nulls="LAST"), UserSignal.created_at.desc())
                .limit(limit)
            )
            if status is not None:
                query = query.where(UserSignal.status == status)
            result: list[dict[str, Any]] = []
            for row in query:
                data = model_to_dict(row) or {}
                data["feed_item_title"] = row.feed_item.title
                data["feed_item_url"] = row.feed_item.canonical_url
                data["source_kind"] = row.feed_item.source.kind
                data["source_title"] = row.feed_item.source.title
                data["topic_name"] = row.topic.name if row.topic_id else None
                result.append(data)
            return result

        return await self._execute(_query, operation_name="list_user_signals", read_only=True)
