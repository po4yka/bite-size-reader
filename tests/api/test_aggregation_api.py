from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.routers.auth.tokens import create_access_token
from app.application.dto.aggregation import (
    MultiSourceAggregationOutput,
    MultiSourceExtractionOutput,
    SourceCoverageEntry,
    SourceExtractionItemResult,
)
from app.application.services.aggregation_rollout import (
    AggregationRolloutDecision,
    AggregationRolloutStage,
)
from app.application.services.multi_source_aggregation_service import (
    MultiSourceAggregationRunResult,
)
from app.config import Config, load_config
from app.di.repositories import build_aggregation_session_repository
from app.domain.models.source import AggregationSessionStatus, SourceItem, SourceKind


def _auth_headers(user_id: int) -> dict[str, str]:
    token = create_access_token(user_id, client_id="test")
    return {"Authorization": f"Bearer {token}"}


def _set_runtime(client, db) -> SimpleNamespace | None:
    runtime = getattr(client.app.state, "runtime", None)
    client.app.state.runtime = SimpleNamespace(
        cfg=load_config(allow_stub_telegram=True),
        db=db,
        background_processor=SimpleNamespace(
            url_processor=SimpleNamespace(content_extractor=MagicMock())
        ),
        core=SimpleNamespace(llm_client=MagicMock()),
    )
    return runtime


def test_create_aggregation_bundle_endpoint_returns_session_and_items(client, db, user_factory):

    allowed_ids = Config.get_allowed_user_ids()
    user_id = int(allowed_ids[0]) if allowed_ids else 424242
    user_factory(username="aggregation_api_user", telegram_user_id=user_id)

    fake_result = MultiSourceAggregationRunResult(
        extraction=MultiSourceExtractionOutput(
            session_id=77,
            correlation_id="cid-agg-create",
            status="completed",
            successful_count=2,
            failed_count=0,
            duplicate_count=0,
            items=[
                SourceExtractionItemResult(
                    position=0,
                    item_id=1001,
                    source_item_id="src_a",
                    source_kind=SourceKind.WEB_ARTICLE,
                    status="extracted",
                    request_id=501,
                ),
                SourceExtractionItemResult(
                    position=1,
                    item_id=1002,
                    source_item_id="src_b",
                    source_kind=SourceKind.X_POST,
                    status="extracted",
                    request_id=502,
                ),
            ],
        ),
        aggregation=MultiSourceAggregationOutput(
            session_id=77,
            correlation_id="cid-agg-create",
            status="completed",
            source_type="mixed",
            total_items=2,
            extracted_items=2,
            used_source_count=2,
            overview="Two-source synthesis",
            source_coverage=[
                SourceCoverageEntry(
                    position=0,
                    item_id=1001,
                    source_item_id="src_a",
                    source_kind=SourceKind.WEB_ARTICLE,
                    status="extracted",
                    used_in_summary=True,
                ),
                SourceCoverageEntry(
                    position=1,
                    item_id=1002,
                    source_item_id="src_b",
                    source_kind=SourceKind.X_POST,
                    status="extracted",
                    used_in_summary=True,
                ),
            ],
        ),
    )

    runtime = _set_runtime(client, db)
    try:
        with patch(
            "app.application.services.multi_source_aggregation_service.MultiSourceAggregationService.aggregate",
            new=AsyncMock(return_value=fake_result),
        ):
            response = client.post(
                "/v1/aggregations",
                headers=_auth_headers(user_id),
                json={
                    "items": [
                        {"url": "https://example.com/article"},
                        {"url": "https://x.com/example/status/1"},
                    ],
                    "lang_preference": "en",
                },
            )
    finally:
        client.app.state.runtime = runtime

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["session"]["sessionId"] == 77
    assert payload["data"]["session"]["sourceType"] == "mixed"
    assert payload["data"]["aggregation"]["overview"] == "Two-source synthesis"
    assert [item["sourceKind"] for item in payload["data"]["items"]] == [
        "web_article",
        "x_post",
    ]


def test_get_aggregation_bundle_endpoint_returns_persisted_session(client, db, user_factory):
    allowed_ids = Config.get_allowed_user_ids()
    user_id = int(allowed_ids[0]) if allowed_ids else 424242
    user_factory(username="aggregation_lookup_user", telegram_user_id=user_id)

    repo = build_aggregation_session_repository(db)
    session_id = asyncio.run(
        repo.async_create_aggregation_session(
            user_id=user_id,
            correlation_id="cid-agg-fetch",
            total_items=2,
            bundle_metadata={"entrypoint": "api"},
        )
    )
    first_source = SourceItem.create(
        kind=SourceKind.WEB_ARTICLE,
        original_value="https://example.com/a",
    )
    second_source = SourceItem.create(
        kind=SourceKind.X_POST,
        original_value="https://x.com/example/status/1",
    )
    asyncio.run(repo.async_add_aggregation_session_item(session_id, first_source, 0))
    asyncio.run(repo.async_add_aggregation_session_item(session_id, second_source, 1))
    asyncio.run(
        repo.async_update_aggregation_session_output(
            session_id,
            {
                "session_id": session_id,
                "correlation_id": "cid-agg-fetch",
                "status": "completed",
                "source_type": "mixed",
                "total_items": 2,
                "extracted_items": 2,
                "used_source_count": 2,
                "overview": "Persisted synthesis output",
            },
        )
    )
    asyncio.run(
        repo.async_update_aggregation_session_status(
            session_id,
            status=AggregationSessionStatus.COMPLETED,
        )
    )
    runtime = getattr(client.app.state, "runtime", None)
    client.app.state.runtime = SimpleNamespace(db=db)
    try:
        response = client.get(
            f"/v1/aggregations/{session_id}",
            headers=_auth_headers(user_id),
        )
    finally:
        client.app.state.runtime = runtime

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["session"]["id"] == session_id
    assert payload["data"]["session"]["correlation_id"] == "cid-agg-fetch"
    assert payload["data"]["aggregation"]["overview"] == "Persisted synthesis output"
    assert [item["source_kind"] for item in payload["data"]["items"]] == [
        "web_article",
        "x_post",
    ]


def test_create_aggregation_bundle_endpoint_returns_404_when_rollout_disabled(
    client, db, user_factory
):
    from app.api.routers.aggregation import _get_rollout_gate

    allowed_ids = Config.get_allowed_user_ids()
    user_id = int(allowed_ids[0]) if allowed_ids else 424242
    user_factory(username="aggregation_api_rollout_user", telegram_user_id=user_id)

    async def _evaluate(_: int) -> AggregationRolloutDecision:
        return AggregationRolloutDecision(
            enabled=False,
            reason="Aggregation bundles are currently disabled.",
            stage=AggregationRolloutStage.DISABLED,
        )

    runtime = _set_runtime(client, db)
    client.app.dependency_overrides[_get_rollout_gate] = lambda: SimpleNamespace(evaluate=_evaluate)
    try:
        response = client.post(
            "/v1/aggregations",
            headers=_auth_headers(user_id),
            json={
                "items": [
                    {"url": "https://example.com/article"},
                    {"url": "https://x.com/example/status/1"},
                ]
            },
        )
    finally:
        client.app.dependency_overrides.pop(_get_rollout_gate, None)
        client.app.state.runtime = runtime

    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["code"] == "NOT_FOUND"
