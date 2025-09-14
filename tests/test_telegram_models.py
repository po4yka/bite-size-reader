"""Unit tests for Telegram message models and validation."""

import unittest
from datetime import datetime
from unittest.mock import Mock

from app.core.telegram_models import (
    ChatType,
    MediaType,
    MessageEntity,
    MessageEntityType,
    TelegramChat,
    TelegramMessage,
    TelegramUser,
)


class TestTelegramUser(unittest.TestCase):
    """Test TelegramUser model."""

    def test_from_dict_basic(self):
        """Test creating TelegramUser from basic dictionary."""
        data = {
            "id": 12345,
            "is_bot": False,
            "first_name": "John",
            "last_name": "Doe",
            "username": "johndoe",
            "language_code": "en",
        }
        user = TelegramUser.from_dict(data)

        self.assertEqual(user.id, 12345)
        self.assertFalse(user.is_bot)
        self.assertEqual(user.first_name, "John")
        self.assertEqual(user.last_name, "Doe")
        self.assertEqual(user.username, "johndoe")
        self.assertEqual(user.language_code, "en")

    def test_from_dict_minimal(self):
        """Test creating TelegramUser from minimal dictionary."""
        data = {
            "id": 12345,
            "is_bot": False,
            "first_name": "John",
        }
        user = TelegramUser.from_dict(data)

        self.assertEqual(user.id, 12345)
        self.assertFalse(user.is_bot)
        self.assertEqual(user.first_name, "John")
        self.assertIsNone(user.last_name)
        self.assertIsNone(user.username)
        self.assertIsNone(user.language_code)


class TestTelegramChat(unittest.TestCase):
    """Test TelegramChat model."""

    def test_from_dict_private(self):
        """Test creating private chat from dictionary."""
        data = {
            "id": 12345,
            "type": "private",
            "first_name": "John",
            "last_name": "Doe",
        }
        chat = TelegramChat.from_dict(data)

        self.assertEqual(chat.id, 12345)
        self.assertEqual(chat.type, ChatType.PRIVATE)
        self.assertEqual(chat.first_name, "John")
        self.assertEqual(chat.last_name, "Doe")
        self.assertIsNone(chat.title)

    def test_from_dict_group(self):
        """Test creating group chat from dictionary."""
        data = {
            "id": -12345,
            "type": "group",
            "title": "Test Group",
        }
        chat = TelegramChat.from_dict(data)

        self.assertEqual(chat.id, -12345)
        self.assertEqual(chat.type, ChatType.GROUP)
        self.assertEqual(chat.title, "Test Group")
        self.assertIsNone(chat.first_name)

    def test_from_dict_channel(self):
        """Test creating channel chat from dictionary."""
        data = {
            "id": -10012345,
            "type": "channel",
            "title": "Test Channel",
            "username": "testchannel",
        }
        chat = TelegramChat.from_dict(data)

        self.assertEqual(chat.id, -10012345)
        self.assertEqual(chat.type, ChatType.CHANNEL)
        self.assertEqual(chat.title, "Test Channel")
        self.assertEqual(chat.username, "testchannel")


class TestMessageEntity(unittest.TestCase):
    """Test MessageEntity model."""

    def test_from_dict_url(self):
        """Test creating URL entity from dictionary."""
        data = {
            "type": "url",
            "offset": 10,
            "length": 20,
        }
        entity = MessageEntity.from_dict(data)

        self.assertEqual(entity.type, MessageEntityType.URL)
        self.assertEqual(entity.offset, 10)
        self.assertEqual(entity.length, 20)
        self.assertIsNone(entity.url)

    def test_from_dict_text_link(self):
        """Test creating text link entity from dictionary."""
        data = {
            "type": "text_link",
            "offset": 10,
            "length": 20,
            "url": "https://example.com",
        }
        entity = MessageEntity.from_dict(data)

        self.assertEqual(entity.type, MessageEntityType.TEXT_LINK)
        self.assertEqual(entity.offset, 10)
        self.assertEqual(entity.length, 20)
        self.assertEqual(entity.url, "https://example.com")

    def test_from_dict_mention(self):
        """Test creating mention entity from dictionary."""
        user_data = {
            "id": 12345,
            "is_bot": False,
            "first_name": "John",
        }
        data = {
            "type": "text_mention",
            "offset": 0,
            "length": 5,
            "user": user_data,
        }
        entity = MessageEntity.from_dict(data)

        self.assertEqual(entity.type, MessageEntityType.TEXT_MENTION)
        self.assertEqual(entity.offset, 0)
        self.assertEqual(entity.length, 5)
        self.assertIsNotNone(entity.user)
        self.assertEqual(entity.user.id, 12345)


class TestTelegramMessage(unittest.TestCase):
    """Test TelegramMessage model."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_message = Mock()
        self.mock_message.id = 12345
        self.mock_message.date = datetime.now()
        self.mock_message.text = "Hello world"
        self.mock_message.caption = None
        self.mock_message.entities = []
        self.mock_message.caption_entities = []
        self.mock_message.photo = None
        self.mock_message.video = None
        self.mock_message.audio = None
        self.mock_message.document = None
        self.mock_message.sticker = None
        self.mock_message.voice = None
        self.mock_message.video_note = None
        self.mock_message.animation = None
        self.mock_message.contact = None
        self.mock_message.location = None
        self.mock_message.venue = None
        self.mock_message.poll = None
        self.mock_message.dice = None
        self.mock_message.game = None
        self.mock_message.invoice = None
        self.mock_message.successful_payment = None
        self.mock_message.story = None
        self.mock_message.forward_from = None
        self.mock_message.forward_from_chat = None
        self.mock_message.forward_from_message_id = None
        self.mock_message.forward_signature = None
        self.mock_message.forward_sender_name = None
        self.mock_message.forward_date = None
        self.mock_message.reply_to_message = None
        self.mock_message.edit_date = None
        self.mock_message.media_group_id = None
        self.mock_message.author_signature = None
        self.mock_message.via_bot = None
        self.mock_message.has_protected_content = None
        self.mock_message.connected_website = None
        self.mock_message.reply_markup = None
        self.mock_message.views = None
        self.mock_message.via_bot_user_id = None
        self.mock_message.effect_id = None
        self.mock_message.link_preview_options = None
        self.mock_message.show_caption_above_media = None

    def test_from_pyrogram_message_basic(self):
        """Test creating TelegramMessage from basic Pyrogram message."""

        # Create a simple object that mimics Pyrogram message structure
        class MockMessage:
            def __init__(self):
                self.id = 12345
                self.date = datetime.now()
                self.text = "Hello world"
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
                self.id = 12345
                self.is_bot = False
                self.first_name = "John"
                self.last_name = "Doe"
                self.username = "johndoe"
                self.language_code = "en"

        class MockChat:
            def __init__(self):
                self.id = 67890
                self.type = "private"
                self.first_name = "John"
                self.last_name = "Doe"

        mock_message = MockMessage()
        mock_message.from_user = MockUser()
        mock_message.chat = MockChat()

        message = TelegramMessage.from_pyrogram_message(mock_message)

        self.assertEqual(message.message_id, 12345)
        self.assertIsNotNone(message.from_user)
        self.assertEqual(message.from_user.id, 12345)
        self.assertIsNotNone(message.chat)
        self.assertEqual(message.chat.id, 67890)
        self.assertEqual(message.text, "Hello world")
        self.assertFalse(message.has_media)
        self.assertTrue(message.has_text)

    def test_from_pyrogram_message_with_photo(self):
        """Test creating TelegramMessage with photo media."""
        # Mock photo
        mock_photo = [Mock(), Mock()]
        mock_photo[0].__dict__ = {"file_id": "photo1", "width": 100, "height": 100}
        mock_photo[1].__dict__ = {"file_id": "photo2", "width": 200, "height": 200}
        self.mock_message.photo = mock_photo

        message = TelegramMessage.from_pyrogram_message(self.mock_message)

        self.assertEqual(message.media_type, MediaType.PHOTO)
        self.assertTrue(message.has_media)
        self.assertIsNotNone(message.photo)
        self.assertEqual(len(message.photo), 2)

    def test_from_pyrogram_message_with_entities(self):
        """Test creating TelegramMessage with entities."""
        # Mock entities
        mock_entity1 = Mock()
        mock_entity1.__dict__ = {
            "type": "url",
            "offset": 0,
            "length": 10,
        }
        mock_entity2 = Mock()
        mock_entity2.__dict__ = {
            "type": "bold",
            "offset": 10,
            "length": 5,
        }
        self.mock_message.entities = [mock_entity1, mock_entity2]

        message = TelegramMessage.from_pyrogram_message(self.mock_message)

        self.assertEqual(len(message.entities), 2)
        self.assertEqual(message.entities[0].type, MessageEntityType.URL)
        self.assertEqual(message.entities[1].type, MessageEntityType.BOLD)

    def test_from_pyrogram_message_forwarded(self):
        """Test creating TelegramMessage with forward information."""

        # Create a simple object that mimics Pyrogram message structure
        class MockMessage:
            def __init__(self):
                self.id = 12345
                self.date = datetime.now()
                self.text = "Hello world"
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

        class MockForwardChat:
            def __init__(self):
                self.id = -10012345
                self.type = "channel"
                self.title = "Test Channel"

        mock_message = MockMessage()
        mock_message.forward_from_chat = MockForwardChat()
        mock_message.forward_from_message_id = 54321

        message = TelegramMessage.from_pyrogram_message(mock_message)

        self.assertTrue(message.is_forwarded)
        self.assertIsNotNone(message.forward_from_chat)
        self.assertEqual(message.forward_from_chat.id, -10012345)
        self.assertEqual(message.forward_from_message_id, 54321)

    def test_validate_basic(self):
        """Test basic message validation."""
        message = TelegramMessage(
            message_id=12345,
            from_user=TelegramUser(
                id=12345,
                is_bot=False,
                first_name="John",
            ),
            text="Hello world",
        )

        errors = message.validate()
        self.assertEqual(len(errors), 0)

    def test_validate_missing_message_id(self):
        """Test validation with missing message ID."""
        message = TelegramMessage(
            message_id=0,
            text="Hello world",
        )

        errors = message.validate()
        self.assertIn("Message ID is required", errors)

    def test_validate_missing_content(self):
        """Test validation with missing content."""
        message = TelegramMessage(
            message_id=12345,
        )

        errors = message.validate()
        self.assertIn("Message must have text, caption, or media content", errors)

    def test_validate_entity_bounds(self):
        """Test validation of entity bounds."""
        message = TelegramMessage(
            message_id=12345,
            text="Hello",
            entities=[
                MessageEntity(
                    type=MessageEntityType.BOLD,
                    offset=0,
                    length=10,  # Extends beyond text length
                )
            ],
        )

        errors = message.validate()
        self.assertIn("Entity extends beyond text length", errors)

    def test_get_effective_text(self):
        """Test getting effective text content."""
        # Test with text
        message = TelegramMessage(
            message_id=12345,
            text="Hello world",
        )
        self.assertEqual(message.get_effective_text(), "Hello world")

        # Test with caption only
        message = TelegramMessage(
            message_id=12345,
            caption="Hello caption",
        )
        self.assertEqual(message.get_effective_text(), "Hello caption")

        # Test with no text or caption
        message = TelegramMessage(
            message_id=12345,
        )
        self.assertIsNone(message.get_effective_text())

    def test_get_effective_entities(self):
        """Test getting effective entities."""
        # Test with text entities
        message = TelegramMessage(
            message_id=12345,
            text="Hello world",
            entities=[
                MessageEntity(
                    type=MessageEntityType.BOLD,
                    offset=0,
                    length=5,
                )
            ],
        )
        self.assertEqual(len(message.get_effective_entities()), 1)

        # Test with caption entities only
        message = TelegramMessage(
            message_id=12345,
            caption="Hello caption",
            caption_entities=[
                MessageEntity(
                    type=MessageEntityType.ITALIC,
                    offset=0,
                    length=5,
                )
            ],
        )
        self.assertEqual(len(message.get_effective_entities()), 1)

    def test_is_command(self):
        """Test command detection."""
        # Test with command
        message = TelegramMessage(
            message_id=12345,
            text="/start hello",
            entities=[
                MessageEntity(
                    type=MessageEntityType.BOT_COMMAND,
                    offset=0,
                    length=6,
                )
            ],
        )
        self.assertTrue(message.is_command())

        # Test without command
        message = TelegramMessage(
            message_id=12345,
            text="Hello world",
            entities=[
                MessageEntity(
                    type=MessageEntityType.BOLD,
                    offset=0,
                    length=5,
                )
            ],
        )
        self.assertFalse(message.is_command())

    def test_get_command(self):
        """Test command extraction."""
        message = TelegramMessage(
            message_id=12345,
            text="/start hello",
            entities=[
                MessageEntity(
                    type=MessageEntityType.BOT_COMMAND,
                    offset=0,
                    length=6,
                )
            ],
        )
        self.assertEqual(message.get_command(), "/start")

    def test_get_urls(self):
        """Test URL extraction."""
        message = TelegramMessage(
            message_id=12345,
            text="Check out https://example.com and https://test.com",
            entities=[
                MessageEntity(
                    type=MessageEntityType.URL,
                    offset=10,  # Correct offset for "https://example.com"
                    length=19,
                ),
                MessageEntity(
                    type=MessageEntityType.URL,
                    offset=34,  # Correct offset for "https://test.com"
                    length=16,
                ),
            ],
        )
        urls = message.get_urls()
        self.assertEqual(len(urls), 2)
        self.assertIn("https://example.com", urls)
        self.assertIn("https://test.com", urls)

    def test_get_media_info(self):
        """Test media information retrieval."""
        # Test with photo
        message = TelegramMessage(
            message_id=12345,
            media_type=MediaType.PHOTO,
            photo=[{"file_id": "photo1", "width": 100, "height": 100}],
        )
        media_info = message.get_media_info()
        self.assertIsNotNone(media_info)
        self.assertEqual(len(media_info), 1)

        # Test without media
        message = TelegramMessage(
            message_id=12345,
            text="Hello world",
        )
        media_info = message.get_media_info()
        self.assertIsNone(media_info)

    def test_to_dict(self):
        """Test conversion to dictionary."""
        message = TelegramMessage(
            message_id=12345,
            from_user=TelegramUser(
                id=12345,
                is_bot=False,
                first_name="John",
            ),
            text="Hello world",
            media_type=MediaType.PHOTO,
        )

        data = message.to_dict()
        self.assertIsInstance(data, dict)
        self.assertEqual(data["message_id"], 12345)
        self.assertEqual(data["text"], "Hello world")
        self.assertEqual(data["media_type"], "photo")
        self.assertIn("from_user", data)


if __name__ == "__main__":
    unittest.main()
