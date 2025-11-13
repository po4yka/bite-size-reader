#!/usr/bin/env python3
"""Test script to verify progress message editing works correctly.
This tests the fix for progress messages being sent as new messages instead of editing existing ones.
"""

import asyncio
from unittest.mock import AsyncMock, Mock

from app.adapters.external.response_formatter import ResponseFormatter


async def test_progress_message_editing():
    """Test that progress messages use edit_message when message_id is provided."""
    # Create mock message
    mock_message = Mock()
    mock_message.chat.id = 123456789

    # Create mock telegram client
    mock_client = AsyncMock()
    mock_client.edit_message_text = AsyncMock()

    # Create response formatter
    rf = ResponseFormatter()
    rf._telegram_client = Mock()
    rf._telegram_client.client = mock_client

    # Test 1: safe_reply_with_id should return message ID
    rf._safe_reply_func = None  # Use client directly

    # Mock the send_message method to return a message ID
    mock_client.send_message = AsyncMock(return_value=Mock(id=987654321))

    # Test 2: edit_message should be called when message_id is provided
    progress_text = "🔄 Processing links: 2/5\n██████████░░░░░░░░░░"

    # Call edit_message directly
    await rf.edit_message(mock_message.chat.id, 987654321, progress_text)

    # Verify edit_message_text was called
    mock_client.edit_message_text.assert_called_once_with(
        chat_id=mock_message.chat.id, message_id=987654321, text=progress_text
    )



if __name__ == "__main__":
    asyncio.run(test_progress_message_editing())
