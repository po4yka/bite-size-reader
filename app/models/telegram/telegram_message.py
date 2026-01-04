"""Telegram Message model with comprehensive validation."""

from __future__ import annotations

import logging
from datetime import datetime  # noqa: TC003 - Pydantic needs this at runtime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.telegram.telegram_chat import TelegramChat
from app.models.telegram.telegram_entity import MessageEntity
from app.models.telegram.telegram_enums import MediaType, MessageEntityType
from app.models.telegram.telegram_user import TelegramUser

logger = logging.getLogger(__name__)


class TelegramMessage(BaseModel):
    """Comprehensive Telegram Message model."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    message_id: int
    from_user: TelegramUser | None = None
    date: datetime | None = None
    chat: TelegramChat | None = None
    text: str | None = None
    entities: list[MessageEntity] = Field(default_factory=list)
    caption: str | None = None
    caption_entities: list[MessageEntity] = Field(default_factory=list)

    # Media fields
    photo: list[dict[str, Any]] | None = None
    photo_list: list[dict[str, Any]] | None = None  # Serialized photo data
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
            photo_list = None
            if photo:
                try:
                    # Handle both single Photo objects and lists of PhotoSize objects
                    if isinstance(photo, list):
                        photo_list = [photo_size.__dict__ for photo_size in photo]
                    else:
                        # Single Photo object - convert to list with single item
                        photo_list = [photo.__dict__]
                except (AttributeError, TypeError) as e:
                    logger.warning(f"Failed to process photo object: {e}")
                    photo_list = None
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
            logger.exception("Failed to parse Telegram message", extra={"error": str(e)})
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
                            last_name=from_user_data.last_name,
                            username=from_user_data.username,
                            language_code=from_user_data.language_code,
                            is_premium=from_user_data.is_premium,
                            added_to_attachment_menu=getattr(
                                from_user_data, "added_to_attachment_menu", None
                            ),
                        )
                except Exception as user_e:
                    logger.warning(
                        "Failed to extract user from failed message", extra={"error": str(user_e)}
                    )
                    # Try to extract just the essential user information
                    try:
                        user_id = getattr(from_user_data, "id", 0)
                        if user_id:
                            from_user = TelegramUser(
                                id=int(user_id),
                                is_bot=False,  # Default fallback
                                first_name="Unknown",  # Default fallback
                                last_name=None,
                                username=None,
                                language_code=None,
                                is_premium=None,
                                added_to_attachment_menu=None,
                            )
                    except Exception:
                        pass  # Give up on user extraction

            # Extract media attributes for error case
            photo_raw = getattr(message, "photo", None)

            # Handle photo serialization for error case
            photo_list = None
            if photo_raw:
                try:
                    # Handle both single Photo objects and lists of PhotoSize objects
                    if isinstance(photo_raw, list):
                        photo_list = [photo_size.__dict__ for photo_size in photo_raw]
                    else:
                        # Single Photo object - convert to list with single item
                        photo_list = [photo_raw.__dict__]
                except (AttributeError, TypeError) as e:
                    logger.warning(f"Failed to process photo object in error case: {e}")
                    photo_list = None

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

            return cls(
                message_id=getattr(message, "id", 0),
                from_user=from_user,
                date=None,
                chat=None,
                text=getattr(message, "text", None),
                caption=getattr(message, "caption", None),
                photo=photo_raw,
                photo_list=photo_list,
                video=video,
                audio=audio,
                document=document,
                sticker=sticker,
                voice=voice,
                video_note=video_note,
                animation=animation,
                contact=contact,
                location=location,
                venue=venue,
                poll=poll,
                dice=dice,
                game=game,
                invoice=invoice,
                successful_payment=successful_payment,
                story=story,
            )

    def _set_computed_fields(self) -> None:
        """Set computed fields based on message content."""
        # Determine media type
        if self.photo or self.photo_list:
            self.media_type = MediaType.PHOTO
        elif self.video:
            self.media_type = MediaType.VIDEO
        elif self.audio:
            self.media_type = MediaType.AUDIO
        elif self.document:
            self.media_type = MediaType.DOCUMENT
        elif self.sticker:
            self.media_type = MediaType.STICKER
        elif self.voice:
            self.media_type = MediaType.VOICE
        elif self.video_note:
            self.media_type = MediaType.VIDEO_NOTE
        elif self.animation:
            self.media_type = MediaType.ANIMATION
        elif self.contact:
            self.media_type = MediaType.CONTACT
        elif self.location:
            self.media_type = MediaType.LOCATION
        elif self.venue:
            self.media_type = MediaType.VENUE
        elif self.poll:
            self.media_type = MediaType.POLL
        elif self.dice:
            self.media_type = MediaType.DICE
        elif self.game:
            self.media_type = MediaType.GAME
        elif self.invoice:
            self.media_type = MediaType.INVOICE
        elif self.successful_payment:
            self.media_type = MediaType.SUCCESSFUL_PAYMENT
        elif self.story:
            self.media_type = MediaType.STORY

        # Set boolean flags
        self.is_forwarded = bool(
            self.forward_from or self.forward_from_chat or self.forward_from_message_id
        )
        self.is_reply = bool(self.reply_to_message)
        self.is_edited = bool(self.edit_date)
        self.has_media = self.media_type is not None
        self.has_text = bool(self.text and self.text.strip())
        self.has_caption = bool(self.caption and self.caption.strip())

    def get_effective_text(self) -> str | None:
        """Get the effective text content (text or caption)."""
        return self.text or self.caption

    def get_effective_entities(self) -> list[MessageEntity]:
        """Get the effective entities (text entities or caption entities)."""
        if self.text and self.entities:
            return self.entities
        if self.caption and self.caption_entities:
            return self.caption_entities
        return []

    def is_command(self) -> bool:
        """Check if message is a bot command."""
        text = self.get_effective_text()
        if not text:
            return False
        return text.startswith("/")

    def get_command(self) -> str | None:
        """Extract command from message text."""
        text = self.get_effective_text()
        if not text or not text.startswith("/"):
            return None

        # Extract command (first word without the /)
        parts = text.split()
        if parts:
            command = parts[0]
            # Handle @botname suffix
            if "@" in command:
                command = command.split("@")[0]
            return command
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        # Use Pydantic's model_dump with custom serialization
        return self.model_dump(mode="json")

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

    def validate_message(self) -> list[str]:
        """Validate message data and return list of validation errors."""
        errors = []

        # Basic validation
        if not isinstance(self.message_id, int) or self.message_id <= 0:
            errors.append("Message ID is required")

        # User validation
        if self.from_user:
            if not isinstance(self.from_user.id, int) or self.from_user.id <= 0:
                errors.append("Invalid from_user.id")
            if not self.from_user.first_name:
                errors.append("Missing from_user.first_name")

        # Chat validation
        if self.chat and not isinstance(self.chat.id, int):
            errors.append("Invalid chat.id")

        # Content validation
        has_valid_content = self.text or self.caption or self.has_media or self.photo_list
        if not has_valid_content:
            errors.append("Message must have text, caption, or media content")

        # Entity validation
        text_len = len(self.text or "")
        for i, entity in enumerate(self.entities):
            offset = entity.offset if isinstance(entity.offset, int) else -1
            length = entity.length if isinstance(entity.length, int) else 0
            end = offset + length

            if offset < 0 or offset >= text_len:
                errors.append(f"Entity {i} offset out of range")
            if length <= 0:
                errors.append(f"Entity {i} length invalid")
            if end > text_len:
                errors.append("Entity extends beyond text length")

        caption_len = len(self.caption or "")
        for i, entity in enumerate(self.caption_entities):
            offset = entity.offset if isinstance(entity.offset, int) else -1
            length = entity.length if isinstance(entity.length, int) else 0
            end = offset + length

            if offset < 0 or offset >= caption_len:
                errors.append(f"Caption entity {i} offset out of range")
            if length <= 0:
                errors.append(f"Caption entity {i} length invalid")
            if end > caption_len:
                errors.append("Caption entity extends beyond text length")

        return errors
