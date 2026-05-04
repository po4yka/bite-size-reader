"""Migrate legacy OpenRouter and Firecrawl response payloads.

Moves provider-specific data into dedicated columns. Idempotent.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-04
"""

from __future__ import annotations

import json
import logging

from alembic import op
from sqlalchemy import text

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | None = None
depends_on: str | None = None

logger = logging.getLogger(__name__)


def upgrade() -> None:
    conn = op.get_bind()
    tables = {
        row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    }

    or_count = 0
    if "llm_calls" in tables:
        rows = conn.execute(text("""
            SELECT id, response_text, response_json,
                   openrouter_response_text, openrouter_response_json
            FROM llm_calls
            WHERE provider = 'openrouter'
              AND (TRIM(COALESCE(response_text, '')) != ''
                   OR TRIM(COALESCE(response_json, '')) != '')
        """)).fetchall()
        for row_id, resp_text, resp_json, or_text, or_json in rows:
            conn.execute(text("""
                UPDATE llm_calls
                SET openrouter_response_text = :ort,
                    openrouter_response_json  = :orj,
                    response_text             = NULL,
                    response_json             = NULL
                WHERE id = :id
            """), {
                "ort": or_text or resp_text,
                "orj": or_json or resp_json,
                "id": row_id,
            })
            or_count += 1

    fc_count = 0
    if "crawl_results" in tables:
        rows = conn.execute(text("""
            SELECT id, raw_response_json
            FROM crawl_results
            WHERE raw_response_json IS NOT NULL
              AND TRIM(raw_response_json) != ''
        """)).fetchall()
        for row_id, raw in rows:
            if isinstance(raw, str):
                try:
                    payload = json.loads(raw)
                except Exception:
                    continue
            elif isinstance(raw, dict):
                payload = raw
            else:
                continue
            if not isinstance(payload, dict):
                continue
            success = payload.get("success")
            if isinstance(success, bool):
                success_val: bool | None = success
            elif isinstance(success, (int, float)):
                success_val = bool(success)
            else:
                success_val = None
            error_code = payload.get("code")
            if error_code is not None:
                error_code = str(error_code)
            error_msg = payload.get("error")
            if error_msg is not None:
                error_msg = str(error_msg)
            details = payload.get("details")
            details_json = json.dumps(details) if details is not None else None
            conn.execute(text("""
                UPDATE crawl_results
                SET firecrawl_success        = :success,
                    firecrawl_error_code     = :code,
                    firecrawl_error_message  = :msg,
                    firecrawl_details_json   = :details,
                    raw_response_json        = NULL
                WHERE id = :id
            """), {
                "success": success_val,
                "code": error_code,
                "msg": error_msg,
                "details": details_json,
                "id": row_id,
            })
            fc_count += 1

    logger.info("legacy_payload_migration openrouter=%d firecrawl=%d", or_count, fc_count)


def downgrade() -> None:
    logger.info("legacy_payload_migration_downgrade_noop: decomposed payloads cannot be reconstructed")
