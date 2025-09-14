"""Telegram message data models and validation based on official Telegram Bot API."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ChatType(Enum):
    """Telegram chat types."""

    PRIVATE = "private"
    GROUP = "group"
    SUPERGROUP = "supergroup"
    CHANNEL = "channel"


class MessageEntityType(Enum):
    """Telegram message entity types."""

    MENTION = "mention"
    HASHTAG = "hashtag"
    CASHTAG = "cashtag"
    BOT_COMMAND = "bot_command"
    URL = "url"
    EMAIL = "email"
    PHONE_NUMBER = "phone_number"
    BOLD = "bold"
    ITALIC = "italic"
    UNDERLINE = "underline"
    STRIKETHROUGH = "strikethrough"
    SPOILER = "spoiler"
    CODE = "code"
    PRE = "pre"
    TEXT_LINK = "text_link"
    TEXT_MENTION = "text_mention"
    CUSTOM_EMOJI = "custom_emoji"


class MediaType(Enum):
    """Telegram media types."""

    PHOTO = "photo"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    STICKER = "sticker"
    VOICE = "voice"
    VIDEO_NOTE = "video_note"
    ANIMATION = "animation"
    CONTACT = "contact"
    LOCATION = "location"
    VENUE = "venue"
    POLL = "poll"
    DICE = "dice"
    GAME = "game"
    INVOICE = "invoice"
    SUCCESSFUL_PAYMENT = "successful_payment"
    STORY = "story"


@dataclass
class TelegramUser:
    """Telegram User object."""

    id: int
    is_bot: bool
    first_name: str
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    is_premium: bool | None = None
    added_to_attachment_menu: bool | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TelegramUser:
        """Create TelegramUser from dictionary."""
        # Ensure ID is always an integer
        user_id = data.get("id", 0)
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            user_id = 0

        return cls(
            id=user_id,
            is_bot=data.get("is_bot", False),
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name"),
            username=data.get("username"),
            language_code=data.get("language_code"),
            is_premium=data.get("is_premium"),
            added_to_attachment_menu=data.get("added_to_attachment_menu"),
        )


@dataclass
class TelegramChat:
    """Telegram Chat object."""

    id: int
    type: ChatType
    title: str | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    is_forum: bool | None = None
    photo: dict[str, Any] | None = None
    active_usernames: list[str] | None = None
    emoji_status_custom_emoji_id: str | None = None
    bio: str | None = None
    has_private_forwards: bool | None = None
    has_restricted_voice_and_video_messages: bool | None = None
    join_to_send_messages: bool | None = None
    join_by_request: bool | None = None
    description: str | None = None
    invite_link: str | None = None
    pinned_message: dict[str, Any] | None = None
    permissions: dict[str, Any] | None = None
    slow_mode_delay: int | None = None
    message_auto_delete_time: int | None = None
    has_aggressive_anti_spam_enabled: bool | None = None
    has_hidden_members: bool | None = None
    has_protected_content: bool | None = None
    sticker_set_name: str | None = None
    can_set_sticker_set: bool | None = None
    linked_chat_id: int | None = None
    location: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TelegramChat:
        """Create TelegramChat from dictionary."""
        # Handle chat type conversion more robustly
        chat_type_str = data.get("type", "private")
        try:
            # Handle both string values and enum objects
            if hasattr(chat_type_str, "value"):
                chat_type_str = chat_type_str.value
            elif hasattr(chat_type_str, "name"):
                chat_type_str = chat_type_str.name.lower()

            # Convert to our enum
            chat_type = ChatType(chat_type_str.lower())
        except (ValueError, AttributeError):
            # Fallback to private if type is unknown
            chat_type = ChatType.PRIVATE

        return cls(
            id=data.get("id", 0),
            type=chat_type,
            title=data.get("title"),
            username=data.get("username"),
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            is_forum=data.get("is_forum"),
            photo=data.get("photo"),
            active_usernames=data.get("active_usernames"),
            emoji_status_custom_emoji_id=data.get("emoji_status_custom_emoji_id"),
            bio=data.get("bio"),
            has_private_forwards=data.get("has_private_forwards"),
            has_restricted_voice_and_video_messages=data.get(
                "has_restricted_voice_and_video_messages"
            ),
            join_to_send_messages=data.get("join_to_send_messages"),
            join_by_request=data.get("join_by_request"),
            description=data.get("description"),
            invite_link=data.get("invite_link"),
            pinned_message=data.get("pinned_message"),
            permissions=data.get("permissions"),
            slow_mode_delay=data.get("slow_mode_delay"),
            message_auto_delete_time=data.get("message_auto_delete_time"),
            has_aggressive_anti_spam_enabled=data.get("has_aggressive_anti_spam_enabled"),
            has_hidden_members=data.get("has_hidden_members"),
            has_protected_content=data.get("has_protected_content"),
            sticker_set_name=data.get("sticker_set_name"),
            can_set_sticker_set=data.get("can_set_sticker_set"),
            linked_chat_id=data.get("linked_chat_id"),
            location=data.get("location"),
        )


@dataclass
class MessageEntity:
    """Telegram MessageEntity object."""

    type: MessageEntityType
    offset: int
    length: int
    url: str | None = None
    user: TelegramUser | None = None
    language: str | None = None
    custom_emoji_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MessageEntity:
        """Create MessageEntity from dictionary."""
        entity_type = MessageEntityType(data.get("type", "mention"))
        user_data = data.get("user")
        user = TelegramUser.from_dict(user_data) if user_data else None

        return cls(
            type=entity_type,
            offset=data.get("offset", 0),
            length=data.get("length", 0),
            url=data.get("url"),
            user=user,
            language=data.get("language"),
            custom_emoji_id=data.get("custom_emoji_id"),
        )


@dataclass
class ForwardInfo:
    """Telegram forward information."""

    from_chat: TelegramChat | None = None
    from_message_id: int | None = None
    signature: str | None = None
    sender_name: str | None = None
    date: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ForwardInfo:
        """Create ForwardInfo from dictionary."""
        from_chat_data = data.get("from_chat")
        from_chat = TelegramChat.from_dict(from_chat_data) if from_chat_data else None

        return cls(
            from_chat=from_chat,
            from_message_id=data.get("from_message_id"),
            signature=data.get("signature"),
            sender_name=data.get("sender_name"),
            date=data.get("date"),
        )


@dataclass
class TelegramMessage:
    """Comprehensive Telegram Message model."""

    message_id: int
    from_user: TelegramUser | None = None
    date: datetime | None = None
    chat: TelegramChat | None = None
    text: str | None = None
    entities: list[MessageEntity] = field(default_factory=list)
    caption: str | None = None
    caption_entities: list[MessageEntity] = field(default_factory=list)

    # Media fields
    photo: list[dict[str, Any]] | None = None
    video: dict[str, Any] | None = None
    audio: dict[str, Any] | None = None
    document: dict[str, Any] | None = None
    sticker: dict[str, Any] | None = None
    voice: dict[str, Any] | None = None
    video_note: dict[str, Any] | None = None
    animation: dict[str, Any] | None = None
    contact: dict[str, Any] | None = None
    location: dict[str, Any] | None = None
    venue: dict[str, Any] | None = None
    poll: dict[str, Any] | None = None
    dice: dict[str, Any] | None = None
    game: dict[str, Any] | None = None
    invoice: dict[str, Any] | None = None
    successful_payment: dict[str, Any] | None = None
    story: dict[str, Any] | None = None

    # Forward/reply fields
    forward_from: TelegramUser | None = None
    forward_from_chat: TelegramChat | None = None
    forward_from_message_id: int | None = None
    forward_signature: str | None = None
    forward_sender_name: str | None = None
    forward_date: datetime | None = None
    reply_to_message: dict[str, Any] | None = None

    # Additional fields
    edit_date: datetime | None = None
    media_group_id: str | None = None
    author_signature: str | None = None
    via_bot: TelegramUser | None = None
    has_protected_content: bool | None = None
    connected_website: str | None = None
    reply_markup: dict[str, Any] | None = None
    views: int | None = None
    via_bot_user_id: int | None = None
    effect_id: str | None = None
    link_preview_options: dict[str, Any] | None = None
    show_caption_above_media: bool | None = None

    # Computed fields
    media_type: MediaType | None = None
    is_forwarded: bool = False
    is_reply: bool = False
    is_edited: bool = False
    has_media: bool = False
    has_text: bool = False
    has_caption: bool = False

    @classmethod
    def from_pyrogram_message(cls, message: Any) -> TelegramMessage:
        """Create TelegramMessage from Pyrogram Message object."""
        try:
            # Extract basic fields
            message_id = getattr(message, "id", 0)
            date = getattr(message, "date", None)

            # Extract user information
            from_user_data = getattr(message, "from_user", None)
            from_user = TelegramUser.from_dict(from_user_data.__dict__) if from_user_data else None

            # Extract chat information
            chat_data = getattr(message, "chat", None)
            chat = TelegramChat.from_dict(chat_data.__dict__) if chat_data else None

            # Extract text content
            text = getattr(message, "text", None)
            caption = getattr(message, "caption", None)

            # Extract entities
            entities = []
            entities_data = getattr(message, "entities", []) or []
            for entity in entities_data:
                try:
                    entity_dict = entity.__dict__ if hasattr(entity, "__dict__") else {}
                    entities.append(MessageEntity.from_dict(entity_dict))
                except Exception as e:
                    logger.warning("Failed to parse entity", extra={"error": str(e)})

            caption_entities = []
            caption_entities_data = getattr(message, "caption_entities", []) or []
            for entity in caption_entities_data:
                try:
                    entity_dict = entity.__dict__ if hasattr(entity, "__dict__") else {}
                    caption_entities.append(MessageEntity.from_dict(entity_dict))
                except Exception as e:
                    logger.warning("Failed to parse caption entity", extra={"error": str(e)})

            # Extract media information
            photo = getattr(message, "photo", None)
            video = getattr(message, "video", None)
            audio = getattr(message, "audio", None)
            document = getattr(message, "document", None)
            sticker = getattr(message, "sticker", None)
            voice = getattr(message, "voice", None)
            video_note = getattr(message, "video_note", None)
            animation = getattr(message, "animation", None)
            contact = getattr(message, "contact", None)
            location = getattr(message, "location", None)
            venue = getattr(message, "venue", None)
            poll = getattr(message, "poll", None)
            dice = getattr(message, "dice", None)
            game = getattr(message, "game", None)
            invoice = getattr(message, "invoice", None)
            successful_payment = getattr(message, "successful_payment", None)
            story = getattr(message, "story", None)

            # Extract forward information
            forward_from = getattr(message, "forward_from", None)
            forward_from_chat = getattr(message, "forward_from_chat", None)
            forward_from_message_id = getattr(message, "forward_from_message_id", None)
            forward_signature = getattr(message, "forward_signature", None)
            forward_sender_name = getattr(message, "forward_sender_name", None)
            forward_date = getattr(message, "forward_date", None)

            # Extract additional fields
            reply_to_message = getattr(message, "reply_to_message", None)
            edit_date = getattr(message, "edit_date", None)
            media_group_id = getattr(message, "media_group_id", None)
            author_signature = getattr(message, "author_signature", None)
            via_bot = getattr(message, "via_bot", None)
            has_protected_content = getattr(message, "has_protected_content", None)
            connected_website = getattr(message, "connected_website", None)
            reply_markup = getattr(message, "reply_markup", None)
            views = getattr(message, "views", None)
            via_bot_user_id = getattr(message, "via_bot_user_id", None)
            effect_id = getattr(message, "effect_id", None)
            link_preview_options = getattr(message, "link_preview_options", None)
            show_caption_above_media = getattr(message, "show_caption_above_media", None)

            # Convert media objects to dictionaries for serialization
            photo_list = [photo_size.__dict__ for photo_size in photo] if photo else None
            video_dict = video.__dict__ if video else None
            audio_dict = audio.__dict__ if audio else None
            document_dict = document.__dict__ if document else None
            sticker_dict = sticker.__dict__ if sticker else None
            voice_dict = voice.__dict__ if voice else None
            video_note_dict = video_note.__dict__ if video_note else None
            animation_dict = animation.__dict__ if animation else None
            contact_dict = contact.__dict__ if contact else None
            location_dict = location.__dict__ if location else None
            venue_dict = venue.__dict__ if venue else None
            poll_dict = poll.__dict__ if poll else None
            dice_dict = dice.__dict__ if dice else None
            game_dict = game.__dict__ if game else None
            invoice_dict = invoice.__dict__ if invoice else None
            successful_payment_dict = successful_payment.__dict__ if successful_payment else None
            story_dict = story.__dict__ if story else None

            # Convert user objects
            forward_from_user = (
                TelegramUser.from_dict(forward_from.__dict__) if forward_from else None
            )
            forward_from_chat_obj = (
                TelegramChat.from_dict(forward_from_chat.__dict__) if forward_from_chat else None
            )
            via_bot_user = TelegramUser.from_dict(via_bot.__dict__) if via_bot else None

            # Convert reply message
            reply_to_message_dict = reply_to_message.__dict__ if reply_to_message else None

            # Determine media type
            media_type = None
            if photo:
                media_type = MediaType.PHOTO
            elif video:
                media_type = MediaType.VIDEO
            elif audio:
                media_type = MediaType.AUDIO
            elif document:
                media_type = MediaType.DOCUMENT
            elif sticker:
                media_type = MediaType.STICKER
            elif voice:
                media_type = MediaType.VOICE
            elif video_note:
                media_type = MediaType.VIDEO_NOTE
            elif animation:
                media_type = MediaType.ANIMATION
            elif contact:
                media_type = MediaType.CONTACT
            elif location:
                media_type = MediaType.LOCATION
            elif venue:
                media_type = MediaType.VENUE
            elif poll:
                media_type = MediaType.POLL
            elif dice:
                media_type = MediaType.DICE
            elif game:
                media_type = MediaType.GAME
            elif invoice:
                media_type = MediaType.INVOICE
            elif successful_payment:
                media_type = MediaType.SUCCESSFUL_PAYMENT
            elif story:
                media_type = MediaType.STORY

            # Compute boolean fields
            is_forwarded = bool(forward_from or forward_from_chat)
            is_reply = bool(reply_to_message)
            is_edited = bool(edit_date)
            has_media = bool(media_type)
            has_text = bool(text)
            has_caption = bool(caption)

            return cls(
                message_id=message_id,
                from_user=from_user,
                date=date,
                chat=chat,
                text=text,
                entities=entities,
                caption=caption,
                caption_entities=caption_entities,
                photo=photo_list,
                video=video_dict,
                audio=audio_dict,
                document=document_dict,
                sticker=sticker_dict,
                voice=voice_dict,
                video_note=video_note_dict,
                animation=animation_dict,
                contact=contact_dict,
                location=location_dict,
                venue=venue_dict,
                poll=poll_dict,
                dice=dice_dict,
                game=game_dict,
                invoice=invoice_dict,
                successful_payment=successful_payment_dict,
                story=story_dict,
                forward_from=forward_from_user,
                forward_from_chat=forward_from_chat_obj,
                forward_from_message_id=forward_from_message_id,
                forward_signature=forward_signature,
                forward_sender_name=forward_sender_name,
                forward_date=forward_date,
                reply_to_message=reply_to_message_dict,
                edit_date=edit_date,
                media_group_id=media_group_id,
                author_signature=author_signature,
                via_bot=via_bot_user,
                has_protected_content=has_protected_content,
                connected_website=connected_website,
                reply_markup=reply_markup,
                views=views,
                via_bot_user_id=via_bot_user_id,
                effect_id=effect_id,
                link_preview_options=link_preview_options,
                show_caption_above_media=show_caption_above_media,
                media_type=media_type,
                is_forwarded=is_forwarded,
                is_reply=is_reply,
                is_edited=is_edited,
                has_media=has_media,
                has_text=has_text,
                has_caption=has_caption,
            )

        except Exception as e:
            logger.error("Failed to parse Telegram message", extra={"error": str(e)})
            # Return minimal message object with best-effort user extraction
            from_user_data = getattr(message, "from_user", None)
            from_user = None
            if from_user_data:
                try:
                    # Extract user ID directly from the raw object
                    user_id = getattr(from_user_data, "id", 0)
                    if user_id:
                        from_user = TelegramUser(
                            id=int(user_id),
                            is_bot=getattr(from_user_data, "is_bot", False),
                            first_name=getattr(from_user_data, "first_name", ""),
                            last_name=getattr(from_user_data, "last_name"),
                            username=getattr(from_user_data, "username"),
                            language_code=getattr(from_user_data, "language_code"),
                            is_premium=getattr(from_user_data, "is_premium"),
                            added_to_attachment_menu=getattr(
                                from_user_data, "added_to_attachment_menu"
                            ),
                        )
                except Exception as user_e:
                    logger.warning(
                        "Failed to extract user from failed message", extra={"error": str(user_e)}
                    )

            return cls(
                message_id=getattr(message, "id", 0),
                from_user=from_user,
                date=None,
                chat=None,
                text=getattr(message, "text", None),
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {}
        for field_name, field_value in self.__dict__.items():
            if isinstance(field_value, Enum):
                result[field_name] = field_value.value
            elif isinstance(field_value, datetime):
                result[field_name] = field_value.isoformat()
            elif isinstance(field_value, TelegramUser | TelegramChat):
                result[field_name] = field_value.__dict__
            elif isinstance(field_value, list):
                result[field_name] = [
                    item.__dict__ if hasattr(item, "__dict__") else item for item in field_value
                ]
            else:
                result[field_name] = field_value
        return result

    def validate(self) -> list[str]:
        """Validate the message and return list of validation errors."""
        errors = []

        # Basic validation
        if not self.message_id:
            errors.append("Message ID is required")

        if not self.from_user and not self.chat:
            errors.append("Either from_user or chat must be present")

        # Text validation
        if not self.text and not self.caption and not self.has_media:
            errors.append("Message must have text, caption, or media content")

        # Entity validation
        for entity in self.entities:
            if entity.offset < 0:
                errors.append(f"Entity offset must be non-negative, got {entity.offset}")
            if entity.length <= 0:
                errors.append(f"Entity length must be positive, got {entity.length}")
            if self.text and entity.offset + entity.length > len(self.text):
                errors.append("Entity extends beyond text length")

        # Caption entity validation
        for entity in self.caption_entities:
            if entity.offset < 0:
                errors.append(f"Caption entity offset must be non-negative, got {entity.offset}")
            if entity.length <= 0:
                errors.append(f"Caption entity length must be positive, got {entity.length}")
            if self.caption and entity.offset + entity.length > len(self.caption):
                errors.append("Caption entity extends beyond caption length")

        # Media validation
        if self.has_media and not self.media_type:
            errors.append("Media type must be specified when media is present")

        # Forward validation
        if self.is_forwarded and not (self.forward_from or self.forward_from_chat):
            errors.append("Forwarded message must have forward source")

        return errors

    def get_media_info(self) -> dict[str, Any] | list[dict[str, Any]] | None:
        """Get media information based on media type."""
        if not self.media_type:
            return None

        media_map = {
            MediaType.PHOTO: self.photo,
            MediaType.VIDEO: self.video,
            MediaType.AUDIO: self.audio,
            MediaType.DOCUMENT: self.document,
            MediaType.STICKER: self.sticker,
            MediaType.VOICE: self.voice,
            MediaType.VIDEO_NOTE: self.video_note,
            MediaType.ANIMATION: self.animation,
            MediaType.CONTACT: self.contact,
            MediaType.LOCATION: self.location,
            MediaType.VENUE: self.venue,
            MediaType.POLL: self.poll,
            MediaType.DICE: self.dice,
            MediaType.GAME: self.game,
            MediaType.INVOICE: self.invoice,
            MediaType.SUCCESSFUL_PAYMENT: self.successful_payment,
            MediaType.STORY: self.story,
        }

        result = media_map.get(self.media_type)
        return result if isinstance(result, dict | list) else None

    def get_effective_text(self) -> str | None:
        """Get the effective text content (text or caption)."""
        return self.text or self.caption

    def get_effective_entities(self) -> list[MessageEntity]:
        """Get the effective entities (entities or caption_entities)."""
        return self.entities if self.text else self.caption_entities

    def is_command(self) -> bool:
        """Check if message is a bot command."""
        if not self.text:
            return False

        for entity in self.entities:
            if entity.type == MessageEntityType.BOT_COMMAND:
                return True
        return False

    def get_command(self) -> str | None:
        """Get the bot command if present."""
        if not self.text:
            return None

        for entity in self.entities:
            if entity.type == MessageEntityType.BOT_COMMAND:
                return self.text[entity.offset : entity.offset + entity.length]
        return None

    def get_urls(self) -> list[str]:
        """Extract URLs from text and entities."""
        urls: list[str] = []

        if not self.text:
            return urls

        for entity in self.entities:
            if entity.type in [MessageEntityType.URL, MessageEntityType.TEXT_LINK]:
                if entity.type == MessageEntityType.URL:
                    # Extract URL from text using entity bounds
                    url = self.text[entity.offset : entity.offset + entity.length]
                else:  # TEXT_LINK
                    # Use the URL from the entity
                    url = entity.url or ""
                if url and url.strip():
                    urls.append(url.strip())

        return urls
