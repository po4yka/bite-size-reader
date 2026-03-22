"""Tests for SmartCollectionHandler event handler.

Complements test_smart_collection.py (which covers domain validation/evaluation)
by testing the handler's orchestration logic with mocked DB access.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.infrastructure.messaging.handlers.smart_collection_handler import (
    SmartCollectionHandler,
)


def _make_event(
    summary_id: int = 1,
    request_id: int = 1,
) -> MagicMock:
    event = MagicMock()
    event.summary_id = summary_id
    event.request_id = request_id
    return event


def _make_collection(
    coll_id: int = 10,
    conditions: list | None = None,
    match_mode: str = "all",
) -> MagicMock:
    coll = MagicMock()
    coll.id = coll_id
    coll.query_conditions_json = conditions
    coll.query_match_mode = match_mode
    return coll


class TestSmartCollectionHandler:
    """Tests for SmartCollectionHandler.on_summary_created."""

    @pytest.fixture
    def handler(self) -> SmartCollectionHandler:
        return SmartCollectionHandler()

    @pytest.mark.asyncio
    async def test_skips_when_no_user_id(self, handler: SmartCollectionHandler) -> None:
        event = _make_event()
        mock_request = MagicMock()
        mock_request.user_id = None

        with patch(
            "app.infrastructure.messaging.handlers.smart_collection_handler.Request"
        ) as MockRequest:
            MockRequest.get_by_id.return_value = mock_request
            await handler.on_summary_created(event)
            # Should return early, no Collection query
            with patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.Collection"
            ) as MockColl:
                MockColl.select.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_no_smart_collections(self, handler: SmartCollectionHandler) -> None:
        event = _make_event()
        mock_request = MagicMock()
        mock_request.user_id = 42

        with (
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.Request"
            ) as MockRequest,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.Collection"
            ) as MockColl,
        ):
            MockRequest.get_by_id.return_value = mock_request
            # Empty list of smart collections
            MockColl.select.return_value.where.return_value = []
            await handler.on_summary_created(event)

    @pytest.mark.asyncio
    async def test_skips_collection_with_empty_conditions(
        self, handler: SmartCollectionHandler
    ) -> None:
        event = _make_event()
        mock_request = MagicMock()
        mock_request.user_id = 42
        coll = _make_collection(conditions=[])

        with (
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.Request"
            ) as MockRequest,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.Collection"
            ) as MockColl,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.Summary"
            ) as MockSummary,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.model_to_dict"
            ) as mock_m2d,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.SummaryTag"
            ) as MockST,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.build_summary_context"
            ) as mock_ctx,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.evaluate_summary"
            ) as mock_eval,
        ):
            MockRequest.get_by_id.return_value = mock_request
            MockColl.select.return_value.where.return_value = [coll]
            MockSummary.get_by_id.return_value = MagicMock()
            mock_m2d.return_value = {}
            MockST.select.return_value.join.return_value.where.return_value = []
            mock_ctx.return_value = {}

            await handler.on_summary_created(event)
            # evaluate_summary should not be called for empty conditions
            mock_eval.assert_not_called()

    @pytest.mark.asyncio
    async def test_adds_matching_summary_to_collection(
        self, handler: SmartCollectionHandler
    ) -> None:
        event = _make_event(summary_id=5, request_id=3)
        mock_request = MagicMock()
        mock_request.user_id = 42
        conditions = [{"type": "domain_matches", "operator": "contains", "value": "arxiv"}]
        coll = _make_collection(coll_id=10, conditions=conditions)

        with (
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.Request"
            ) as MockRequest,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.Collection"
            ) as MockColl,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.Summary"
            ) as MockSummary,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.model_to_dict"
            ) as mock_m2d,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.SummaryTag"
            ) as MockST,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.build_summary_context"
            ) as mock_ctx,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.evaluate_summary"
            ) as mock_eval,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.CollectionItem"
            ) as MockCI,
        ):
            MockRequest.get_by_id.return_value = mock_request
            MockColl.select.return_value.where.return_value = [coll]
            MockSummary.get_by_id.return_value = MagicMock()
            mock_m2d.return_value = {}
            MockST.select.return_value.join.return_value.where.return_value = []
            mock_ctx.return_value = {
                "url": "https://arxiv.org/abs/123",
                "title": "",
                "tags": [],
                "language": "",
                "reading_time": 0,
                "source_type": "",
                "content": "",
            }
            mock_eval.return_value = True
            # Item does not exist yet
            MockCI.select.return_value.where.return_value.exists.return_value = False
            MockCI.select.return_value.where.return_value.scalar.return_value = 0

            await handler.on_summary_created(event)

            mock_eval.assert_called_once_with(conditions, mock_ctx.return_value, "all")
            MockCI.create.assert_called_once()
            create_kwargs = MockCI.create.call_args.kwargs
            assert create_kwargs["collection"] == 10
            assert create_kwargs["summary"] == 5
            assert create_kwargs["position"] == 1

    @pytest.mark.asyncio
    async def test_skips_duplicate_item(self, handler: SmartCollectionHandler) -> None:
        event = _make_event(summary_id=5, request_id=3)
        mock_request = MagicMock()
        mock_request.user_id = 42
        conditions = [{"type": "domain_matches", "operator": "contains", "value": "arxiv"}]
        coll = _make_collection(coll_id=10, conditions=conditions)

        with (
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.Request"
            ) as MockRequest,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.Collection"
            ) as MockColl,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.Summary"
            ) as MockSummary,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.model_to_dict"
            ) as mock_m2d,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.SummaryTag"
            ) as MockST,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.build_summary_context"
            ) as mock_ctx,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.evaluate_summary"
            ) as mock_eval,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.CollectionItem"
            ) as MockCI,
        ):
            MockRequest.get_by_id.return_value = mock_request
            MockColl.select.return_value.where.return_value = [coll]
            MockSummary.get_by_id.return_value = MagicMock()
            mock_m2d.return_value = {}
            MockST.select.return_value.join.return_value.where.return_value = []
            mock_ctx.return_value = {}
            mock_eval.return_value = True
            # Item already exists
            MockCI.select.return_value.where.return_value.exists.return_value = True

            await handler.on_summary_created(event)
            MockCI.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_exception_is_caught_and_logged(self, handler: SmartCollectionHandler) -> None:
        event = _make_event()

        with (
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.Request"
            ) as MockRequest,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.logger"
            ) as mock_logger,
        ):
            MockRequest.get_by_id.side_effect = Exception("DB down")
            # Should not raise
            await handler.on_summary_created(event)
            mock_logger.exception.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_matching_summary_not_added(self, handler: SmartCollectionHandler) -> None:
        event = _make_event()
        mock_request = MagicMock()
        mock_request.user_id = 42
        conditions = [{"type": "domain_matches", "operator": "contains", "value": "github"}]
        coll = _make_collection(conditions=conditions)

        with (
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.Request"
            ) as MockRequest,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.Collection"
            ) as MockColl,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.Summary"
            ) as MockSummary,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.model_to_dict"
            ) as mock_m2d,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.SummaryTag"
            ) as MockST,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.build_summary_context"
            ) as mock_ctx,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.evaluate_summary"
            ) as mock_eval,
            patch(
                "app.infrastructure.messaging.handlers.smart_collection_handler.CollectionItem"
            ) as MockCI,
        ):
            MockRequest.get_by_id.return_value = mock_request
            MockColl.select.return_value.where.return_value = [coll]
            MockSummary.get_by_id.return_value = MagicMock()
            mock_m2d.return_value = {}
            MockST.select.return_value.join.return_value.where.return_value = []
            mock_ctx.return_value = {}
            mock_eval.return_value = False

            await handler.on_summary_created(event)
            MockCI.create.assert_not_called()
