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


def _auth_headers(user_id: int, client_id: str = "test") -> dict[str, str]:
    token = create_access_token(user_id, client_id=client_id)
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
    assert payload["data"]["session"]["progress"]["completionPercent"] == 100
    assert payload["data"]["aggregation"]["overview"] == "Two-source synthesis"
    assert [item["sourceKind"] for item in payload["data"]["items"]] == [
        "web_article",
        "x_post",
    ]


def test_create_aggregation_bundle_endpoint_audits_and_passes_client_id_metadata(
    client, db, user_factory
):
    allowed_ids = Config.get_allowed_user_ids()
    user_id = int(allowed_ids[0]) if allowed_ids else 424242
    user_factory(username="aggregation_api_audit_user", telegram_user_id=user_id)

    fake_result = MultiSourceAggregationRunResult(
        extraction=MultiSourceExtractionOutput(
            session_id=701,
            correlation_id="cid-agg-audit",
            status="completed",
            successful_count=1,
            failed_count=0,
            duplicate_count=0,
            items=[
                SourceExtractionItemResult(
                    position=0,
                    item_id=9001,
                    source_item_id="src_audit",
                    source_kind=SourceKind.WEB_ARTICLE,
                    status="extracted",
                    request_id=801,
                ),
            ],
        ),
        aggregation=MultiSourceAggregationOutput(
            session_id=701,
            correlation_id="cid-agg-audit",
            status="completed",
            source_type="web_article",
            total_items=1,
            extracted_items=1,
            used_source_count=1,
            overview="Audited aggregation",
            source_coverage=[
                SourceCoverageEntry(
                    position=0,
                    item_id=9001,
                    source_item_id="src_audit",
                    source_kind=SourceKind.WEB_ARTICLE,
                    status="extracted",
                    used_in_summary=True,
                ),
            ],
        ),
    )

    aggregate_mock = AsyncMock(return_value=fake_result)
    audit_mock = MagicMock()
    runtime = _set_runtime(client, db)
    try:
        with (
            patch(
                "app.application.services.multi_source_aggregation_service.MultiSourceAggregationService.aggregate",
                new=aggregate_mock,
            ),
            patch(
                "app.api.routers.aggregation.build_async_audit_sink",
                return_value=audit_mock,
            ),
        ):
            response = client.post(
                "/v1/aggregations",
                headers=_auth_headers(user_id, client_id="cli-audit-v1"),
                json={
                    "items": [
                        {"url": "https://example.com/article"},
                    ],
                    "metadata": {"submitted_by": "test"},
                },
            )
    finally:
        client.app.state.runtime = runtime

    assert response.status_code == 200
    aggregate_kwargs = aggregate_mock.await_args.kwargs
    assert aggregate_kwargs["metadata"]["entrypoint"] == "api"
    assert aggregate_kwargs["metadata"]["client_id"] == "cli-audit-v1"
    assert aggregate_kwargs["metadata"]["submitted_by"] == "test"
    assert [call.args[1] for call in audit_mock.call_args_list] == [
        "aggregation.bundle_create_requested",
        "aggregation.bundle_create_succeeded",
    ]
    assert audit_mock.call_args_list[0].args[2]["client_id"] == "cli-audit-v1"
    assert audit_mock.call_args_list[1].args[2]["session_id"] == 701


def test_create_aggregation_bundle_endpoint_accepts_single_item(client, db, user_factory):
    allowed_ids = Config.get_allowed_user_ids()
    user_id = int(allowed_ids[0]) if allowed_ids else 424242
    user_factory(username="aggregation_api_single_user", telegram_user_id=user_id)

    fake_result = MultiSourceAggregationRunResult(
        extraction=MultiSourceExtractionOutput(
            session_id=78,
            correlation_id="cid-agg-single",
            status="completed",
            successful_count=1,
            failed_count=0,
            duplicate_count=0,
            items=[
                SourceExtractionItemResult(
                    position=0,
                    item_id=1101,
                    source_item_id="src_single",
                    source_kind=SourceKind.WEB_ARTICLE,
                    status="extracted",
                    request_id=601,
                ),
            ],
        ),
        aggregation=MultiSourceAggregationOutput(
            session_id=78,
            correlation_id="cid-agg-single",
            status="completed",
            source_type="web_article",
            total_items=1,
            extracted_items=1,
            used_source_count=1,
            overview="Single-source synthesis",
            source_coverage=[
                SourceCoverageEntry(
                    position=0,
                    item_id=1101,
                    source_item_id="src_single",
                    source_kind=SourceKind.WEB_ARTICLE,
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
                    ],
                    "lang_preference": "en",
                },
            )
    finally:
        client.app.state.runtime = runtime

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["session"]["sessionId"] == 78
    assert payload["data"]["session"]["successfulCount"] == 1
    assert payload["data"]["aggregation"]["source_type"] == "web_article"
    assert [item["sourceKind"] for item in payload["data"]["items"]] == ["web_article"]


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
            status=AggregationSessionStatus.PROCESSING,
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
    assert payload["data"]["session"]["started_at"] is not None
    assert payload["data"]["session"]["completed_at"] is not None
    assert payload["data"]["session"]["progress"]["completionPercent"] == 0
    assert payload["data"]["aggregation"]["overview"] == "Persisted synthesis output"
    assert [item["source_kind"] for item in payload["data"]["items"]] == [
        "web_article",
        "x_post",
    ]


def test_list_aggregation_bundles_endpoint_returns_only_authenticated_user_sessions(
    client, db, user_factory
):
    allowed_ids = Config.get_allowed_user_ids()
    primary_user_id = int(allowed_ids[0]) if allowed_ids else 424242
    secondary_user_id = primary_user_id + 1
    user_factory(username="aggregation_list_primary", telegram_user_id=primary_user_id)
    user_factory(username="aggregation_list_secondary", telegram_user_id=secondary_user_id)

    repo = build_aggregation_session_repository(db)
    first_session_id = asyncio.run(
        repo.async_create_aggregation_session(
            user_id=primary_user_id,
            correlation_id="cid-agg-list-1",
            total_items=3,
        )
    )
    asyncio.run(
        repo.async_update_aggregation_session_counts(
            first_session_id,
            successful_count=2,
            failed_count=1,
            duplicate_count=0,
        )
    )
    asyncio.run(
        repo.async_update_aggregation_session_status(
            first_session_id,
            status=AggregationSessionStatus.PARTIAL,
        )
    )
    asyncio.run(
        repo.async_create_aggregation_session(
            user_id=secondary_user_id,
            correlation_id="cid-agg-list-2",
            total_items=1,
        )
    )

    runtime = getattr(client.app.state, "runtime", None)
    client.app.state.runtime = SimpleNamespace(db=db)
    try:
        response = client.get(
            "/v1/aggregations?limit=20&offset=0",
            headers=_auth_headers(primary_user_id),
        )
    finally:
        client.app.state.runtime = runtime

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert [session["id"] for session in payload["data"]["sessions"]] == [first_session_id]
    assert payload["data"]["sessions"][0]["status"] == AggregationSessionStatus.PARTIAL.value
    assert payload["data"]["sessions"][0]["started_at"] is not None
    assert payload["data"]["sessions"][0]["completed_at"] is not None
    assert payload["data"]["sessions"][0]["progress"]["completionPercent"] == 100
    assert payload["meta"]["pagination"]["hasMore"] is False


def test_create_aggregation_bundle_endpoint_rejects_invalid_source_kind_hint(
    client, db, user_factory
):
    allowed_ids = Config.get_allowed_user_ids()
    user_id = int(allowed_ids[0]) if allowed_ids else 424242
    user_factory(username="aggregation_invalid_hint_user", telegram_user_id=user_id)

    runtime = _set_runtime(client, db)
    try:
        response = client.post(
            "/v1/aggregations",
            headers=_auth_headers(user_id),
            json={
                "items": [
                    {
                        "url": "https://example.com/article",
                        "source_kind_hint": "unknown_kind",
                    }
                ],
            },
        )
    finally:
        client.app.state.runtime = runtime

    assert response.status_code == 422


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
