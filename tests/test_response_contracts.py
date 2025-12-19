from app.api.context import correlation_id_ctx
from app.api.models.responses import ErrorDetail, error_response, success_response


def test_success_response_uses_context_correlation_id() -> None:
    token = correlation_id_ctx.set("cid-ctx-1")
    try:
        resp = success_response({"foo": "bar"})
    finally:
        correlation_id_ctx.reset(token)

    assert resp["success"] is True
    assert resp["data"] == {"foo": "bar"}
    assert resp["meta"]["correlation_id"] == "cid-ctx-1"
    assert resp["meta"]["version"]


def test_success_response_includes_pagination_meta() -> None:
    pagination = {"total": 10, "limit": 5, "offset": 0, "has_more": True}
    resp = success_response({"items": []}, pagination=pagination)

    # Pagination uses serialization aliases (hasMore instead of has_more)
    expected_pagination = {"total": 10, "limit": 5, "offset": 0, "hasMore": True}
    assert resp["meta"]["pagination"] == expected_pagination
    assert resp["success"] is True


def test_error_response_sets_correlation_id() -> None:
    token = correlation_id_ctx.set("cid-error-1")
    try:
        detail = ErrorDetail(code="ERR_TEST", message="boom")
        resp = error_response(detail)
    finally:
        correlation_id_ctx.reset(token)

    assert resp["success"] is False
    assert resp["error"]["code"] == "ERR_TEST"
    assert resp["error"]["correlation_id"] == "cid-error-1"
    assert resp["meta"]["correlation_id"] == "cid-error-1"
