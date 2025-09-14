"""Unit tests for enum parsing fixes in Telegram models."""

import unittest

from app.core.telegram_models import ChatType, MessageEntity, MessageEntityType, TelegramChat


class TestChatTypeEnumParsing(unittest.TestCase):
    """Test ChatType enum parsing fixes."""

    def test_from_dict_string_value(self):
        """Test parsing string chat type values."""
        data = {
            "id": 12345,
            "type": "private",
            "first_name": "John",
        }
        chat = TelegramChat.from_dict(data)
        self.assertEqual(chat.type, ChatType.PRIVATE)

    def test_from_dict_enum_object_with_value(self):
        """Test parsing enum object with value attribute."""

        class MockEnum:
            def __init__(self, value):
                self.value = value

        data = {
            "id": 12345,
            "type": MockEnum("group"),
            "title": "Test Group",
        }
        chat = TelegramChat.from_dict(data)
        self.assertEqual(chat.type, ChatType.GROUP)

    def test_from_dict_enum_object_with_name(self):
        """Test parsing enum object with name attribute."""

        class MockEnum:
            def __init__(self, name):
                self.name = name

        data = {
            "id": 12345,
            "type": MockEnum("CHANNEL"),
            "title": "Test Channel",
        }
        chat = TelegramChat.from_dict(data)
        self.assertEqual(chat.type, ChatType.CHANNEL)

    def test_from_dict_invalid_type_fallback(self):
        """Test fallback to PRIVATE for invalid chat types."""
        data = {
            "id": 12345,
            "type": "invalid_type",
            "first_name": "John",
        }
        chat = TelegramChat.from_dict(data)
        self.assertEqual(chat.type, ChatType.PRIVATE)

    def test_from_dict_none_type_fallback(self):
        """Test fallback to PRIVATE for None chat type."""
        data = {
            "id": 12345,
            "type": None,
            "first_name": "John",
        }
        chat = TelegramChat.from_dict(data)
        self.assertEqual(chat.type, ChatType.PRIVATE)

    def test_from_dict_missing_type_fallback(self):
        """Test fallback to PRIVATE for missing chat type."""
        data = {
            "id": 12345,
            "first_name": "John",
        }
        chat = TelegramChat.from_dict(data)
        self.assertEqual(chat.type, ChatType.PRIVATE)

    def test_from_dict_uppercase_string(self):
        """Test parsing uppercase string values."""
        data = {
            "id": 12345,
            "type": "SUPERGROUP",
            "title": "Test Supergroup",
        }
        chat = TelegramChat.from_dict(data)
        self.assertEqual(chat.type, ChatType.SUPERGROUP)


class TestMessageEntityTypeEnumParsing(unittest.TestCase):
    """Test MessageEntityType enum parsing fixes."""

    def test_from_dict_string_value(self):
        """Test parsing string entity type values."""
        data = {
            "type": "url",
            "offset": 0,
            "length": 10,
        }
        entity = MessageEntity.from_dict(data)
        self.assertEqual(entity.type, MessageEntityType.URL)

    def test_from_dict_enum_object_with_value(self):
        """Test parsing enum object with value attribute."""

        class MockEnum:
            def __init__(self, value):
                self.value = value

        data = {
            "type": MockEnum("bot_command"),
            "offset": 0,
            "length": 6,
        }
        entity = MessageEntity.from_dict(data)
        self.assertEqual(entity.type, MessageEntityType.BOT_COMMAND)

    def test_from_dict_enum_object_with_name(self):
        """Test parsing enum object with name attribute."""

        class MockEnum:
            def __init__(self, name):
                self.name = name

        data = {
            "type": MockEnum("TEXT_LINK"),
            "offset": 0,
            "length": 10,
            "url": "https://example.com",
        }
        entity = MessageEntity.from_dict(data)
        self.assertEqual(entity.type, MessageEntityType.TEXT_LINK)

    def test_from_dict_invalid_type_fallback(self):
        """Test fallback to MENTION for invalid entity types."""
        data = {
            "type": "invalid_type",
            "offset": 0,
            "length": 10,
        }
        entity = MessageEntity.from_dict(data)
        self.assertEqual(entity.type, MessageEntityType.MENTION)

    def test_from_dict_none_type_fallback(self):
        """Test fallback to MENTION for None entity type."""
        data = {
            "type": None,
            "offset": 0,
            "length": 10,
        }
        entity = MessageEntity.from_dict(data)
        self.assertEqual(entity.type, MessageEntityType.MENTION)

    def test_from_dict_missing_type_fallback(self):
        """Test fallback to MENTION for missing entity type."""
        data = {
            "offset": 0,
            "length": 10,
        }
        entity = MessageEntity.from_dict(data)
        self.assertEqual(entity.type, MessageEntityType.MENTION)

    def test_from_dict_uppercase_string(self):
        """Test parsing uppercase string values."""
        data = {
            "type": "HASHTAG",
            "offset": 0,
            "length": 5,
        }
        entity = MessageEntity.from_dict(data)
        self.assertEqual(entity.type, MessageEntityType.HASHTAG)

    def test_from_dict_pyrogram_enum_simulation(self):
        """Test parsing simulated Pyrogram enum objects."""

        class PyrogramEnum:
            def __init__(self, name):
                self.name = name
                self.value = name.lower()

        data = {
            "type": PyrogramEnum("BOT_COMMAND"),
            "offset": 0,
            "length": 6,
        }
        entity = MessageEntity.from_dict(data)
        self.assertEqual(entity.type, MessageEntityType.BOT_COMMAND)


if __name__ == "__main__":
    unittest.main()
