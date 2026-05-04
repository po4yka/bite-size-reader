"""Tests for CancelledError propagation and debug logging in ResponseProcessor."""

from __future__ import annotations

import asyncio
import unittest

from app.adapters.openrouter.response_processor import ResponseProcessor


class TestContentWalkLogging(unittest.TestCase):
    """Verify that content walk failures are logged at debug level."""

    def test_content_walk_failure_logs_debug(self) -> None:
        """When walk_content raises, a debug log 'content_walk_failed' must be emitted."""
        from unittest.mock import patch

        proc = ResponseProcessor(enable_stats=False)

        class BadDict(dict):
            """A dict whose __contains__ raises an exception."""

            def __contains__(self, key):
                raise RuntimeError("Intentional error for testing")

        message_obj: dict = {"content": [BadDict()]}

        with patch("app.adapters.openrouter.response_processor.logger") as mock_logger:
            result = proc.extract_structured_content(message_obj, rf_included=False)

        self.assertIsNone(result)
        mock_logger.warning.assert_called_once()
        self.assertIn("content_walk_failed", mock_logger.warning.call_args[0][0])

    def test_content_walk_reraises_cancelled_error(self) -> None:
        """CancelledError must not be swallowed by the content walk except block."""
        proc = ResponseProcessor(enable_stats=False)

        class CancellingList(list):
            """A list whose iteration raises CancelledError."""

            def __iter__(self):
                raise asyncio.CancelledError()

        message_obj: dict = {"content": CancellingList([1])}

        with self.assertRaises(asyncio.CancelledError):
            proc.extract_structured_content(message_obj, rf_included=False)


class TestToolCallExtractionLogging(unittest.TestCase):
    """Verify that tool-call extraction failures are logged at debug level."""

    def test_tool_call_extraction_failure_logs_debug(self) -> None:
        """When tool_call arg parsing raises, a debug log must be emitted."""
        from unittest.mock import patch

        proc = ResponseProcessor(enable_stats=False)

        message_obj: dict = {
            "tool_calls": [{"function": "not_a_dict"}],
        }

        with patch("app.adapters.openrouter.response_processor.logger") as mock_logger:
            result = proc.extract_structured_content(message_obj, rf_included=False)

        self.assertIsNone(result)
        mock_logger.warning.assert_called_once()
        self.assertIn("tool_call_extraction_failed", mock_logger.warning.call_args[0][0])

    def test_tool_call_extraction_reraises_cancelled_error(self) -> None:
        """CancelledError must not be swallowed by the tool-call except block."""
        proc = ResponseProcessor(enable_stats=False)

        class CancellingDict(dict):
            """A dict whose get("function") raises CancelledError."""

            def get(self, key, default=None):
                if key == "function":
                    raise asyncio.CancelledError()
                return super().get(key, default)

        # Must be non-empty so `tool_calls[0] or {}` doesn't replace it
        message_obj: dict = {
            "tool_calls": [CancellingDict({"_": 1})],
        }

        with self.assertRaises(asyncio.CancelledError):
            proc.extract_structured_content(message_obj, rf_included=False)


if __name__ == "__main__":
    unittest.main()
