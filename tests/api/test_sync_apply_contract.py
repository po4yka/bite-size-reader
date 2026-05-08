"""Sync /v1/sync/apply response shape contract.

Locks the JSON shape that ratatoskr-client (and the KMP client behind
[[map-ratatoskr-mobile-api-contract-to-kmp-readiness]]) consume:
sessionId / results[] / conflicts[]? / hasMore?, with camelCase aliases on
every nested envelope. Failures here mean a backend change has shifted
the wire format and the client needs to re-validate.
"""

from __future__ import annotations

from app.api.models.responses import (
    SyncApplyItemResult,
    SyncApplyResponseData,
    success_response,
)


def _success_item(entity_type: str, id_: int | str, server_version: int) -> SyncApplyItemResult:
    return SyncApplyItemResult(
        entity_type=entity_type,
        id=id_,
        status="applied",
        server_version=server_version,
    )


def _conflict_item(
    entity_type: str,
    id_: int | str,
    server_version: int,
    server_snapshot: dict,
    error_code: str = "version_mismatch",
) -> SyncApplyItemResult:
    return SyncApplyItemResult(
        entity_type=entity_type,
        id=id_,
        status="conflict",
        server_version=server_version,
        server_snapshot=server_snapshot,
        error_code=error_code,
    )


def test_apply_response_serializes_camelcase_top_level() -> None:
    response = SyncApplyResponseData(
        session_id="sync-session-abc",
        results=[_success_item("summary", 42, 7)],
    )
    payload = response.model_dump(by_alias=True, exclude_none=True)

    # Top-level keys are camelCase aliases, not snake_case attribute names.
    assert set(payload.keys()) == {"sessionId", "results"}
    assert payload["sessionId"] == "sync-session-abc"


def test_apply_response_item_uses_camelcase_aliases() -> None:
    response = SyncApplyResponseData(
        session_id="sync-session-abc",
        results=[_success_item("summary", 42, 7)],
    )
    item = response.model_dump(by_alias=True, exclude_none=True)["results"][0]

    assert item == {
        "entityType": "summary",
        "id": 42,
        "status": "applied",
        "serverVersion": 7,
    }


def test_apply_response_includes_conflict_with_full_aliases() -> None:
    response = SyncApplyResponseData(
        session_id="sync-session-abc",
        results=[
            _success_item("summary", 42, 7),
            _conflict_item(
                entity_type="summary",
                id_=43,
                server_version=12,
                server_snapshot={"id": 43, "title": "server-side title"},
            ),
        ],
        conflicts=[
            _conflict_item(
                entity_type="summary",
                id_=43,
                server_version=12,
                server_snapshot={"id": 43, "title": "server-side title"},
            )
        ],
    )
    payload = response.model_dump(by_alias=True, exclude_none=True)

    assert payload["conflicts"][0] == {
        "entityType": "summary",
        "id": 43,
        "status": "conflict",
        "serverVersion": 12,
        "serverSnapshot": {"id": 43, "title": "server-side title"},
        "errorCode": "version_mismatch",
    }


def test_apply_response_has_more_round_trips_as_camelcase() -> None:
    truthy = SyncApplyResponseData(
        session_id="sync-session-abc",
        results=[_success_item("summary", 1, 1)],
        has_more=True,
    )
    payload_truthy = truthy.model_dump(by_alias=True, exclude_none=True)
    assert payload_truthy["hasMore"] is True
    assert "has_more" not in payload_truthy

    # Default (None): omitted under exclude_none — matches the OpenAPI optional.
    omitted = SyncApplyResponseData(
        session_id="sync-session-abc",
        results=[_success_item("summary", 1, 1)],
    )
    assert "hasMore" not in omitted.model_dump(by_alias=True, exclude_none=True)


def test_apply_response_envelope_via_success_response_helper() -> None:
    response = SyncApplyResponseData(
        session_id="sync-session-abc",
        results=[_success_item("summary", 42, 7)],
    )
    envelope = success_response(response)

    # Outer envelope shape: success / data / meta. data is the camelCase apply
    # payload — this is what the client actually parses.
    assert envelope["success"] is True
    assert "data" in envelope
    assert envelope["data"]["sessionId"] == "sync-session-abc"
    assert envelope["data"]["results"][0]["entityType"] == "summary"
    assert envelope["data"]["results"][0]["serverVersion"] == 7
    assert "meta" in envelope
