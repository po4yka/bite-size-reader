"""Migrate legacy OpenRouter and Firecrawl response payloads.

This migration moves data that was previously re-processed on every startup
into a one-time versioned operation:

1. OpenRouter payloads: Moves response_text/response_json into the
   provider-specific openrouter_response_text/openrouter_response_json
   columns for rows where provider='openrouter'.

2. Firecrawl raw payloads: Extracts structured fields (success, error_code,
   error_message, details) from raw_response_json into dedicated columns,
   then clears raw_response_json.

Both operations are idempotent -- rows that have already been migrated
(e.g. by the old inline code) will be skipped.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import peewee
from peewee import fn

if TYPE_CHECKING:
    from app.db.session import DatabaseSessionManager

logger = logging.getLogger(__name__)


def _prepare_json_payload(value: Any, *, default: Any | None = None) -> Any | None:
    """Minimal JSON payload preparation for migration use.

    Avoids importing app.db.json_utils to keep migration self-contained.
    """
    if value is None:
        value = default
    if value is None:
        return None
    if isinstance(value, dict | list):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return stripped
    return value


def _migrate_openrouter_payloads(db_instance: peewee.SqliteDatabase) -> int:
    """Move OpenRouter response data to provider-specific columns."""
    from app.db.models import LLMCall

    if "llm_calls" not in db_instance.get_tables():
        return 0

    # Only process rows where provider=openrouter AND generic response fields
    # still have data (i.e. not yet migrated)
    rows = (
        LLMCall.select()
        .where(
            (LLMCall.provider == "openrouter")
            & (
                (LLMCall.response_text.is_null(False) & (fn.trim(LLMCall.response_text) != ""))
                | (LLMCall.response_json.is_null(False) & (fn.trim(LLMCall.response_json) != ""))
            )
        )
        .iterator()
    )

    updated = 0
    for row in rows:
        new_openrouter_json = row.openrouter_response_json or row.response_json
        new_openrouter_text = row.openrouter_response_text or row.response_text
        LLMCall.update(
            {
                LLMCall.openrouter_response_text: new_openrouter_text,
                LLMCall.openrouter_response_json: new_openrouter_json,
                LLMCall.response_text: None,
                LLMCall.response_json: None,
            }
        ).where(LLMCall.id == row.id).execute()
        updated += 1

    if updated:
        logger.info("openrouter_payload_migrated", extra={"rows": updated})
    return updated


def _migrate_firecrawl_payloads(db_instance: peewee.SqliteDatabase) -> int:
    """Extract structured fields from raw_response_json into dedicated columns."""
    from app.db.models import CrawlResult

    if "crawl_results" not in db_instance.get_tables():
        return 0

    rows = (
        CrawlResult.select()
        .where(
            (CrawlResult.raw_response_json.is_null(False))
            & (fn.trim(CrawlResult.raw_response_json) != "")
        )
        .iterator()
    )

    updated = 0
    for row in rows:
        raw_value = row.raw_response_json
        if not raw_value:
            continue

        if isinstance(raw_value, dict | list):
            payload = raw_value
        else:
            try:
                payload = json.loads(raw_value)
            except Exception as exc:
                logger.debug(
                    "firecrawl_migration_json_error",
                    extra={"error": str(exc), "row_id": row.id},
                )
                continue

        if not isinstance(payload, Mapping):
            continue

        success_val = payload.get("success")
        success_bool: bool | None
        if isinstance(success_val, bool):
            success_bool = success_val
        elif isinstance(success_val, int | float):
            success_bool = bool(success_val)
        else:
            success_bool = None

        error_code = payload.get("code")
        if error_code is not None and not isinstance(error_code, str):
            error_code = str(error_code)

        error_message = payload.get("error")
        if error_message is not None and not isinstance(error_message, str):
            error_message = str(error_message)

        details = payload.get("details")
        details_json = _prepare_json_payload(details)

        CrawlResult.update(
            {
                CrawlResult.firecrawl_success: success_bool,
                CrawlResult.firecrawl_error_code: error_code,
                CrawlResult.firecrawl_error_message: error_message,
                CrawlResult.firecrawl_details_json: details_json,
                CrawlResult.raw_response_json: None,
            }
        ).where(CrawlResult.id == row.id).execute()
        updated += 1

    if updated:
        logger.info("firecrawl_payload_migrated", extra={"rows": updated})
    return updated


def upgrade(db: DatabaseSessionManager) -> None:
    """Migrate legacy OpenRouter and Firecrawl response payloads."""
    db_instance = getattr(db, "database", getattr(db, "_database", None))
    if db_instance is None:
        msg = "Cannot resolve database instance from db object"
        raise TypeError(msg)

    or_count = _migrate_openrouter_payloads(db_instance)
    fc_count = _migrate_firecrawl_payloads(db_instance)

    logger.info(
        "legacy_payload_migration_complete",
        extra={"openrouter_rows": or_count, "firecrawl_rows": fc_count},
    )


def downgrade(db: DatabaseSessionManager) -> None:
    """Payload migration is not reversible.

    The original raw_response_json data has been decomposed into structured
    columns.  Reconstructing the original blob is not feasible without the
    original response.  Downgrade is a no-op.
    """
    logger.warning(
        "legacy_payload_downgrade_noop",
        extra={"reason": "Decomposed payloads cannot be reconstructed"},
    )
