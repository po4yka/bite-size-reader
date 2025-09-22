"""Unit tests for user validation fixes."""

import os
import tempfile
import unittest
from unittest.mock import patch

from app.adapters.telegram.telegram_bot import TelegramBot
from app.config import AppConfig, FirecrawlConfig, OpenRouterConfig, RuntimeConfig, TelegramConfig
from app.db.database import Database
from app.models.telegram.telegram_models import ChatType, TelegramMessage, TelegramUser


class FakeMessage:
    """Fake message for testing."""

    def __init__(self, text: str, uid: int, message_id: int = 101):
        class _User:
            def __init__(self, id):
                self.id = id

        class _Chat:
            id = 1

        self.text = text
        self.chat = _Chat()
        self.from_user = _User(uid)
        self._replies: list[str] = []
        self.id = message_id
        self.message_id = message_id

    async def reply_text(self, text):
        self._replies.append(text)


def make_bot(tmp_path: str, allowed_ids):
    """Create a test bot instance."""
    db = Database(tmp_path)
    db.migrate()
    cfg = AppConfig(
        telegram=TelegramConfig(
            api_id=0, api_hash="", bot_token="", allowed_user_ids=tuple(allowed_ids)
        ),
        firecrawl=FirecrawlConfig(api_key="fc-dummy-key"),
        openrouter=OpenRouterConfig(
            api_key="or-dummy-key",
            model="openai/gpt-4o-mini",
            fallback_models=tuple(),
            http_referer=None,
            x_title=None,
            max_tokens=None,
            top_p=None,
            temperature=0.2,
        ),
        runtime=RuntimeConfig(
            db_path=tmp_path,
            log_level="INFO",
            request_timeout_sec=5,
            preferred_lang="en",
            debug_payloads=False,
        ),
    )
    from app.adapters import telegram_bot as tbmod

    setattr(tbmod, "Client", object)
    setattr(tbmod, "filters", None)
    return TelegramBot(cfg=cfg, db=db)


class TestUserValidationFixes(unittest.IsolatedAsyncioTestCase):
    """Test user validation fixes."""

    async def test_user_id_type_consistency(self):
        """Test that user ID type consistency is maintained."""
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"), allowed_ids=[94225168])

            # Test with integer user ID
            msg = FakeMessage("/help", uid=94225168)
            await bot._on_message(msg)

            # Should be allowed
            self.assertTrue(any("commands" in reply.lower() for reply in msg._replies))

    async def test_user_id_string_conversion(self):
        """Test that string user IDs are properly converted to integers."""
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"), allowed_ids=[94225168])

            # Create a message with string user ID that gets converted
            class StringUserMessage(FakeMessage):
                def __init__(self, text: str, uid_str: str):
                    super().__init__(text, 0)  # Will be overridden
                    self.from_user.id = uid_str  # String ID

            msg = StringUserMessage("/help", "94225168")
            await bot._on_message(msg)

            # Should be allowed after conversion
            self.assertTrue(any("commands" in reply.lower() for reply in msg._replies))

    async def test_user_id_validation_with_different_types(self):
        """Test user validation with different ID types."""
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"), allowed_ids=[94225168, 12345])

            # Disable rate limiting for the test
            bot.response_formatter.MIN_MESSAGE_INTERVAL_MS = 0

            # Test with integer
            msg1 = FakeMessage("/help", uid=94225168)
            await bot._on_message(msg1)
            self.assertTrue(any("commands" in reply.lower() for reply in msg1._replies))

            # Test with different integer
            msg2 = FakeMessage("/help", uid=12345)
            await bot._on_message(msg2)
            self.assertTrue(any("commands" in reply.lower() for reply in msg2._replies))

            # Test with denied user
            msg3 = FakeMessage("/help", uid=99999)
            await bot._on_message(msg3)
            self.assertTrue(any("denied" in reply.lower() for reply in msg3._replies))

    async def test_telegram_message_parsing_with_enum_objects(self):
        """Test TelegramMessage parsing with Pyrogram enum objects."""

        # Test ChatType enum object parsing
        class MockChatType:
            def __init__(self, name):
                self.name = name
                self.value = name.lower()

        class MockMessage:
            def __init__(self):
                self.id = 12345
                self.date = None
                self.text = "Test message"
                self.caption = None
                self.entities = []
                self.caption_entities = []
                self.photo = None
                self.video = None
                self.audio = None
                self.document = None
                self.sticker = None
                self.voice = None
                self.video_note = None
                self.animation = None
                self.contact = None
                self.location = None
                self.venue = None
                self.poll = None
                self.dice = None
                self.game = None
                self.invoice = None
                self.successful_payment = None
                self.story = None
                self.forward_from = None
                self.forward_from_chat = None
                self.forward_from_message_id = None
                self.forward_signature = None
                self.forward_sender_name = None
                self.forward_date = None
                self.reply_to_message = None
                self.edit_date = None
                self.media_group_id = None
                self.author_signature = None
                self.via_bot = None
                self.has_protected_content = None
                self.connected_website = None
                self.reply_markup = None
                self.views = None
                self.via_bot_user_id = None
                self.effect_id = None
                self.link_preview_options = None
                self.show_caption_above_media = None

        class MockUser:
            def __init__(self):
                self.id = 94225168
                self.is_bot = False
                self.first_name = "Test"
                self.last_name = "User"
                self.username = "testuser"
                self.language_code = "en"
                self.is_premium = None
                self.added_to_attachment_menu = None

        class MockChat:
            def __init__(self):
                self.id = 94225168
                self.type = MockChatType("PRIVATE")  # Enum object
                self.first_name = "Test"
                self.last_name = "User"
                self.title = None
                self.username = None
                self.is_forum = None
                self.photo = None
                self.active_usernames = None
                self.emoji_status_custom_emoji_id = None
                self.bio = None
                self.has_private_forwards = None
                self.has_restricted_voice_and_video_messages = None
                self.has_restricted_voice_and_video_messages_for_self = None
                self.description = None
                self.invite_link = None
                self.pinned_message = None
                self.permissions = None
                self.slow_mode_delay = None
                self.message_auto_delete_time = None
                self.has_aggressive_anti_spam_enabled = None
                self.has_hidden_members = None
                self.has_protected_content = None
                self.sticker_set_name = None
                self.can_set_sticker_set = None
                self.linked_chat_id = None
                self.location = None

        mock_message = MockMessage()
        mock_message.from_user = MockUser()
        mock_message.chat = MockChat()

        # Test parsing
        telegram_message = TelegramMessage.from_pyrogram_message(mock_message)

        # Should parse successfully
        self.assertEqual(telegram_message.message_id, 12345)
        self.assertIsNotNone(telegram_message.from_user)
        self.assertEqual(telegram_message.from_user.id, 94225168)
        self.assertIsNotNone(telegram_message.chat)
        self.assertEqual(telegram_message.chat.type, ChatType.PRIVATE)

    async def test_telegram_user_id_conversion(self):
        """Test TelegramUser ID conversion from various types."""
        # Test with integer
        user_data_int = {
            "id": 94225168,
            "is_bot": False,
            "first_name": "Test",
        }
        user_int = TelegramUser.from_dict(user_data_int)
        self.assertEqual(user_int.id, 94225168)
        self.assertIsInstance(user_int.id, int)

        # Test with string
        user_data_str = {
            "id": "94225168",
            "is_bot": False,
            "first_name": "Test",
        }
        user_str = TelegramUser.from_dict(user_data_str)
        self.assertEqual(user_str.id, 94225168)
        self.assertIsInstance(user_str.id, int)

        # Test with invalid string
        user_data_invalid = {
            "id": "invalid",
            "is_bot": False,
            "first_name": "Test",
        }
        user_invalid = TelegramUser.from_dict(user_data_invalid)
        self.assertEqual(user_invalid.id, 0)  # Should fallback to 0

        # Test with None
        user_data_none = {
            "id": None,
            "is_bot": False,
            "first_name": "Test",
        }
        user_none = TelegramUser.from_dict(user_data_none)
        self.assertEqual(user_none.id, 0)  # Should fallback to 0

    async def test_empty_allowed_user_ids_raises(self):
        """Empty allowed user IDs should now be rejected during initialization."""
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                make_bot(os.path.join(tmp, "app.db"), allowed_ids=[])

    async def test_user_validation_logging(self):
        """Test that user validation logging works correctly."""
        with tempfile.TemporaryDirectory() as tmp:
            bot = make_bot(os.path.join(tmp, "app.db"), allowed_ids=[94225168])

            # Capture log output
            with patch("app.adapters.telegram_bot.logger") as mock_logger:
                msg = FakeMessage("/help", uid=94225168)
                await bot._on_message(msg)

                # Check that logging was called
                mock_logger.info.assert_called()

                # Check that the log contains user ID information
                log_calls = [call.args for call in mock_logger.info.call_args_list]
                self.assertTrue(any("94225168" in str(call) for call in log_calls))


if __name__ == "__main__":
    unittest.main()
