"""baseline_sqlalchemy_continuation

Revision ID: 0001b
Revises: 0001
Create Date: 2026-05-06 12:58:54.039002
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001b"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "user_devices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("platform", sa.Text(), nullable=False),
        sa.Column("device_id", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_index("ix_user_devices_token", "user_devices", ["token"], unique=True)
    op.create_index(
        "ix_user_devices_user_id_platform", "user_devices", ["user_id", "platform"], unique=False
    )
    op.create_table(
        "user_digest_preferences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("delivery_time", sa.Text(), nullable=True),
        sa.Column("timezone", sa.Text(), nullable=True),
        sa.Column("hours_lookback", sa.Integer(), nullable=True),
        sa.Column("max_posts_per_digest", sa.Integer(), nullable=True),
        sa.Column("min_relevance_score", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_table(
        "user_goals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("goal_type", sa.Text(), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False),
        sa.Column("scope_type", sa.Text(), nullable=False),
        sa.Column("scope_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_user_goals_user_id_goal_type_scope_type",
        "user_goals",
        ["user_id", "goal_type", "scope_type"],
        unique=False,
    )
    op.create_table(
        "user_interactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("interaction_type", sa.Text(), nullable=False),
        sa.Column("command", sa.Text(), nullable=True),
        sa.Column("input_text", sa.Text(), nullable=True),
        sa.Column("input_url", sa.Text(), nullable=True),
        sa.Column("has_forward", sa.Boolean(), nullable=False),
        sa.Column("forward_from_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("forward_from_chat_title", sa.Text(), nullable=True),
        sa.Column("forward_from_message_id", sa.Integer(), nullable=True),
        sa.Column("media_type", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.Text(), nullable=True),
        sa.Column("structured_output_enabled", sa.Boolean(), nullable=False),
        sa.Column("response_sent", sa.Boolean(), nullable=False),
        sa.Column("response_type", sa.Text(), nullable=True),
        sa.Column("error_occurred", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("processing_time_ms", sa.Integer(), nullable=True),
        sa.Column("request_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["requests.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_user_interactions_request_id", "user_interactions", ["request_id"], unique=False
    )
    op.create_index("ix_user_interactions_user_id", "user_interactions", ["user_id"], unique=False)
    op.create_table(
        "video_downloads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.Text(), nullable=False),
        sa.Column("video_file_path", sa.Text(), nullable=True),
        sa.Column("subtitle_file_path", sa.Text(), nullable=True),
        sa.Column("metadata_file_path", sa.Text(), nullable=True),
        sa.Column("thumbnail_file_path", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("channel", sa.Text(), nullable=True),
        sa.Column("channel_id", sa.Text(), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("upload_date", sa.Text(), nullable=True),
        sa.Column("view_count", sa.BigInteger(), nullable=True),
        sa.Column("like_count", sa.BigInteger(), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("video_codec", sa.Text(), nullable=True),
        sa.Column("audio_codec", sa.Text(), nullable=True),
        sa.Column("format_id", sa.Text(), nullable=True),
        sa.Column("subtitle_language", sa.Text(), nullable=True),
        sa.Column("auto_generated", sa.Boolean(), nullable=True),
        sa.Column("transcript_text", sa.Text(), nullable=True),
        sa.Column("transcript_source", sa.Text(), nullable=True),
        sa.Column("download_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("download_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["request_id"], ["requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id"),
    )
    op.create_index(
        "ix_video_downloads_created_at", "video_downloads", ["created_at"], unique=False
    )
    op.create_index("ix_video_downloads_status", "video_downloads", ["status"], unique=False)
    op.create_index("ix_video_downloads_video_id", "video_downloads", ["video_id"], unique=False)
    op.create_table(
        "webhook_subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("secret", sa.Text(), nullable=False),
        sa.Column("events_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("last_delivery_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("server_version", sa.BigInteger(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_webhook_subscriptions_user_id_enabled",
        "webhook_subscriptions",
        ["user_id", "enabled"],
        unique=False,
    )
    op.create_table(
        "aggregation_session_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("aggregation_session_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("source_item_id", sa.Text(), nullable=False),
        sa.Column("source_dedupe_key", sa.Text(), nullable=False),
        sa.Column("original_value", sa.Text(), nullable=True),
        sa.Column("normalized_value", sa.Text(), nullable=True),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_message_id", sa.Integer(), nullable=True),
        sa.Column("telegram_media_group_id", sa.Text(), nullable=True),
        sa.Column("title_hint", sa.Text(), nullable=True),
        sa.Column("source_metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "normalized_document_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "extraction_metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("duplicate_of_item_id", sa.Integer(), nullable=True),
        sa.Column("failure_code", sa.Text(), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("failure_details_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["aggregation_session_id"], ["aggregation_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["request_id"], ["requests.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_aggregation_session_items_duplicate_of_item_id",
        "aggregation_session_items",
        ["duplicate_of_item_id"],
        unique=False,
    )
    op.create_index(
        "ix_aggregation_session_items_request_id",
        "aggregation_session_items",
        ["request_id"],
        unique=False,
    )
    op.create_index(
        "ix_aggregation_session_items_session_position",
        "aggregation_session_items",
        ["aggregation_session_id", "position"],
        unique=True,
    )
    op.create_index(
        "ix_aggregation_session_items_session_source_item",
        "aggregation_session_items",
        ["aggregation_session_id", "source_item_id"],
        unique=False,
    )
    op.create_index(
        "ix_aggregation_session_items_status", "aggregation_session_items", ["status"], unique=False
    )
    op.create_table(
        "audio_generations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("summary_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("voice_id", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("duration_sec", sa.Float(), nullable=True),
        sa.Column("char_count", sa.Integer(), nullable=True),
        sa.Column("source_field", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["summary_id"], ["summaries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("summary_id"),
    )
    op.create_index(
        "ix_audio_generations_created_at", "audio_generations", ["created_at"], unique=False
    )
    op.create_index("ix_audio_generations_status", "audio_generations", ["status"], unique=False)
    op.create_table(
        "batch_session_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_session_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_series_part", sa.Boolean(), nullable=False),
        sa.Column("series_order", sa.Integer(), nullable=True),
        sa.Column("series_title", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["batch_session_id"], ["batch_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["request_id"], ["requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_batch_session_items_is_series_part",
        "batch_session_items",
        ["is_series_part"],
        unique=False,
    )
    op.create_index(
        "ix_batch_session_items_session_position",
        "batch_session_items",
        ["batch_session_id", "position"],
        unique=False,
    )
    op.create_index(
        "ix_batch_session_items_session_request",
        "batch_session_items",
        ["batch_session_id", "request_id"],
        unique=True,
    )
    op.create_table(
        "channel_post_analyses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("real_topic", sa.Text(), nullable=False),
        sa.Column("tldr", sa.Text(), nullable=False),
        sa.Column("key_insights", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("relevance_score", sa.Float(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("llm_call_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["llm_call_id"], ["llm_calls.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["post_id"], ["channel_posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("post_id"),
    )
    op.create_table(
        "channel_subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["channel_categories.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_channel_subscriptions_user_id_channel_id",
        "channel_subscriptions",
        ["user_id", "channel_id"],
        unique=True,
    )
    op.create_table(
        "collection_collaborators",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("invited_by_id", sa.BigInteger(), nullable=True),
        sa.Column("server_version", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["invited_by_id"],
            ["users.telegram_user_id"],
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_collection_collaborators_collection_id_user_id",
        "collection_collaborators",
        ["collection_id", "user_id"],
        unique=True,
    )
    op.create_index(
        "ix_collection_collaborators_user_id", "collection_collaborators", ["user_id"], unique=False
    )
    op.create_table(
        "collection_invites",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invited_email", sa.Text(), nullable=True),
        sa.Column("invited_user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("server_version", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_index(
        "ix_collection_invites_collection_id", "collection_invites", ["collection_id"], unique=False
    )
    op.create_index("ix_collection_invites_status", "collection_invites", ["status"], unique=False)
    op.create_table(
        "collection_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("summary_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["summary_id"], ["summaries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_collection_items_collection_id_position",
        "collection_items",
        ["collection_id", "position"],
        unique=False,
    )
    op.create_index(
        "ix_collection_items_collection_id_summary_id",
        "collection_items",
        ["collection_id", "summary_id"],
        unique=True,
    )
    op.create_table(
        "feed_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("views", sa.Integer(), nullable=True),
        sa.Column("forwards", sa.Integer(), nullable=True),
        sa.Column("comments", sa.Integer(), nullable=True),
        sa.Column("engagement_score", sa.Float(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("legacy_rss_item_id", sa.Integer(), nullable=True),
        sa.Column("legacy_channel_post_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["legacy_channel_post_id"], ["channel_posts.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["legacy_rss_item_id"], ["rss_feed_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("legacy_channel_post_id"),
        sa.UniqueConstraint("legacy_rss_item_id"),
    )
    op.create_index("ix_feed_items_canonical_url", "feed_items", ["canonical_url"], unique=False)
    op.create_index("ix_feed_items_published_at", "feed_items", ["published_at"], unique=False)
    op.create_index(
        "ix_feed_items_source_id_external_id",
        "feed_items",
        ["source_id", "external_id"],
        unique=True,
    )
    op.create_table(
        "rss_feed_subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("feed_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["channel_categories.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["feed_id"], ["rss_feeds.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rss_feed_subscriptions_user_id_feed_id",
        "rss_feed_subscriptions",
        ["user_id", "feed_id"],
        unique=True,
    )
    op.create_table(
        "rss_item_deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("summary_request_id", sa.Integer(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["rss_feed_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rss_item_deliveries_user_id_item_id",
        "rss_item_deliveries",
        ["user_id", "item_id"],
        unique=True,
    )
    op.create_table(
        "rule_execution_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("summary_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("matched", sa.Boolean(), nullable=False),
        sa.Column("conditions_result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("actions_taken_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["rule_id"], ["automation_rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["summary_id"], ["summaries.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rule_execution_logs_created_at", "rule_execution_logs", ["created_at"], unique=False
    )
    op.create_index(
        "ix_rule_execution_logs_rule_id", "rule_execution_logs", ["rule_id"], unique=False
    )
    op.create_table(
        "summary_embeddings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("summary_id", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("model_version", sa.Text(), nullable=False),
        sa.Column("embedding_blob", sa.LargeBinary(), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["summary_id"], ["summaries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("summary_id"),
    )
    op.create_index(
        "ix_summary_embeddings_model_name_model_version",
        "summary_embeddings",
        ["model_name", "model_version"],
        unique=False,
    )
    op.create_table(
        "summary_feedbacks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("summary_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("issues", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["summary_id"], ["summaries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_summary_feedbacks_user_id_summary_id",
        "summary_feedbacks",
        ["user_id", "summary_id"],
        unique=True,
    )
    op.create_table(
        "summary_highlights",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("summary_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=True),
        sa.Column("end_offset", sa.Integer(), nullable=True),
        sa.Column("color", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("server_version", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["summary_id"], ["summaries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_summary_highlights_updated_at", "summary_highlights", ["updated_at"], unique=False
    )
    op.create_index(
        "ix_summary_highlights_user_id_summary_id",
        "summary_highlights",
        ["user_id", "summary_id"],
        unique=False,
    )
    op.create_table(
        "summary_tags",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("summary_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("server_version", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["summary_id"], ["summaries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_summary_tags_summary_id_tag_id", "summary_tags", ["summary_id", "tag_id"], unique=True
    )
    op.create_index("ix_summary_tags_tag_id", "summary_tags", ["tag_id"], unique=False)
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["webhook_subscriptions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_webhook_deliveries_created_at", "webhook_deliveries", ["created_at"], unique=False
    )
    op.create_index(
        "ix_webhook_deliveries_subscription_id",
        "webhook_deliveries",
        ["subscription_id"],
        unique=False,
    )
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("cadence_seconds", sa.Integer(), nullable=True),
        sa.Column("next_fetch_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("topic_constraints_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("legacy_rss_subscription_id", sa.Integer(), nullable=True),
        sa.Column("legacy_channel_subscription", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["legacy_rss_subscription_id"], ["rss_feed_subscriptions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("legacy_channel_subscription"),
        sa.UniqueConstraint("legacy_rss_subscription_id"),
    )
    op.create_index(
        "ix_subscriptions_next_fetch_at", "subscriptions", ["next_fetch_at"], unique=False
    )
    op.create_index(
        "ix_subscriptions_user_id_is_active",
        "subscriptions",
        ["user_id", "is_active"],
        unique=False,
    )
    op.create_index(
        "ix_subscriptions_user_id_source_id", "subscriptions", ["user_id", "source_id"], unique=True
    )
    op.create_table(
        "user_signals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("feed_item_id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("heuristic_score", sa.Float(), nullable=True),
        sa.Column("llm_score", sa.Float(), nullable=True),
        sa.Column("final_score", sa.Float(), nullable=True),
        sa.Column("filter_stage", sa.Text(), nullable=False),
        sa.Column("evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("llm_judge_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("llm_cost_usd", sa.Float(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["feed_item_id"], ["feed_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_signals_final_score", "user_signals", ["final_score"], unique=False)
    op.create_index(
        "ix_user_signals_user_id_feed_item_id",
        "user_signals",
        ["user_id", "feed_item_id"],
        unique=True,
    )
    op.create_index(
        "ix_user_signals_user_id_status", "user_signals", ["user_id", "status"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_user_signals_user_id_status", table_name="user_signals")
    op.drop_index("ix_user_signals_user_id_feed_item_id", table_name="user_signals")
    op.drop_index("ix_user_signals_final_score", table_name="user_signals")
    op.drop_table("user_signals")
    op.drop_index("ix_subscriptions_user_id_source_id", table_name="subscriptions")
    op.drop_index("ix_subscriptions_user_id_is_active", table_name="subscriptions")
    op.drop_index("ix_subscriptions_next_fetch_at", table_name="subscriptions")
    op.drop_table("subscriptions")
    op.drop_index("ix_webhook_deliveries_subscription_id", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_created_at", table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")
    op.drop_index("ix_summary_tags_tag_id", table_name="summary_tags")
    op.drop_index("ix_summary_tags_summary_id_tag_id", table_name="summary_tags")
    op.drop_table("summary_tags")
    op.drop_index("ix_summary_highlights_user_id_summary_id", table_name="summary_highlights")
    op.drop_index("ix_summary_highlights_updated_at", table_name="summary_highlights")
    op.drop_table("summary_highlights")
    op.drop_index("ix_summary_feedbacks_user_id_summary_id", table_name="summary_feedbacks")
    op.drop_table("summary_feedbacks")
    op.drop_index("ix_summary_embeddings_model_name_model_version", table_name="summary_embeddings")
    op.drop_table("summary_embeddings")
    op.drop_index("ix_rule_execution_logs_rule_id", table_name="rule_execution_logs")
    op.drop_index("ix_rule_execution_logs_created_at", table_name="rule_execution_logs")
    op.drop_table("rule_execution_logs")
    op.drop_index("ix_rss_item_deliveries_user_id_item_id", table_name="rss_item_deliveries")
    op.drop_table("rss_item_deliveries")
    op.drop_index("ix_rss_feed_subscriptions_user_id_feed_id", table_name="rss_feed_subscriptions")
    op.drop_table("rss_feed_subscriptions")
    op.drop_index("ix_feed_items_source_id_external_id", table_name="feed_items")
    op.drop_index("ix_feed_items_published_at", table_name="feed_items")
    op.drop_index("ix_feed_items_canonical_url", table_name="feed_items")
    op.drop_table("feed_items")
    op.drop_index("ix_collection_items_collection_id_summary_id", table_name="collection_items")
    op.drop_index("ix_collection_items_collection_id_position", table_name="collection_items")
    op.drop_table("collection_items")
    op.drop_index("ix_collection_invites_status", table_name="collection_invites")
    op.drop_index("ix_collection_invites_collection_id", table_name="collection_invites")
    op.drop_table("collection_invites")
    op.drop_index("ix_collection_collaborators_user_id", table_name="collection_collaborators")
    op.drop_index(
        "ix_collection_collaborators_collection_id_user_id", table_name="collection_collaborators"
    )
    op.drop_table("collection_collaborators")
    op.drop_index("ix_channel_subscriptions_user_id_channel_id", table_name="channel_subscriptions")
    op.drop_table("channel_subscriptions")
    op.drop_table("channel_post_analyses")
    op.drop_index("ix_batch_session_items_session_request", table_name="batch_session_items")
    op.drop_index("ix_batch_session_items_session_position", table_name="batch_session_items")
    op.drop_index("ix_batch_session_items_is_series_part", table_name="batch_session_items")
    op.drop_table("batch_session_items")
    op.drop_index("ix_audio_generations_status", table_name="audio_generations")
    op.drop_index("ix_audio_generations_created_at", table_name="audio_generations")
    op.drop_table("audio_generations")
    op.drop_index("ix_aggregation_session_items_status", table_name="aggregation_session_items")
    op.drop_index(
        "ix_aggregation_session_items_session_source_item", table_name="aggregation_session_items"
    )
    op.drop_index(
        "ix_aggregation_session_items_session_position", table_name="aggregation_session_items"
    )
    op.drop_index("ix_aggregation_session_items_request_id", table_name="aggregation_session_items")
    op.drop_index(
        "ix_aggregation_session_items_duplicate_of_item_id", table_name="aggregation_session_items"
    )
    op.drop_table("aggregation_session_items")
    op.drop_index("ix_webhook_subscriptions_user_id_enabled", table_name="webhook_subscriptions")
    op.drop_table("webhook_subscriptions")
    op.drop_index("ix_video_downloads_video_id", table_name="video_downloads")
    op.drop_index("ix_video_downloads_status", table_name="video_downloads")
    op.drop_index("ix_video_downloads_created_at", table_name="video_downloads")
    op.drop_table("video_downloads")
    op.drop_index("ix_user_interactions_user_id", table_name="user_interactions")
    op.drop_index("ix_user_interactions_request_id", table_name="user_interactions")
    op.drop_table("user_interactions")
    op.drop_index("ix_user_goals_user_id_goal_type_scope_type", table_name="user_goals")
    op.drop_table("user_goals")
    op.drop_table("user_digest_preferences")
    op.drop_index("ix_user_devices_user_id_platform", table_name="user_devices")
    op.drop_index("ix_user_devices_token", table_name="user_devices")
    op.drop_table("user_devices")
