"""CocoIndex flow: summaries table -> Qdrant vector store.

This module defines the incremental ETL flow that keeps Qdrant in sync with
the Postgres `summaries` table. CocoIndex handles watermark tracking,
LISTEN/NOTIFY change detection, and idempotent upserts.

The flow emits ONE point per summary (not chunked windows). This is a
deliberate v1 simplification; chunked points are a follow-up task after
measuring retrieval quality on production queries.

CocoIndex API note: this targets cocoindex>=1.0.3,<1.1. If the installed
version differs, verify the flow_def, fn, sources, and targets APIs
against the installed package's documentation.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.logging_utils import get_logger
from app.infrastructure.cocoindex.embedding_bridge import embed_text_sync, summary_id_to_point_id

logger = get_logger(__name__)


def _extract_indexable_text(json_payload: str | dict[str, Any] | None) -> str:
    """Extract the text we embed from a summary's json_payload.

    Mirrors the logic in app.core.embedding_text.prepare_text_for_embedding
    but operates on the raw payload without the token-length truncation
    (CocoIndex handles batching/chunking at the flow level).
    """
    if not json_payload:
        return ""
    if isinstance(json_payload, str):
        try:
            payload = json.loads(json_payload)
        except (json.JSONDecodeError, ValueError):
            return json_payload[:2000]
    else:
        payload = json_payload

    parts: list[str] = []
    metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
    title = metadata.get("title") or payload.get("title") or ""
    if title:
        parts.append(title)
    for key in ("summary_1000", "summary_250", "tldr"):
        val = payload.get(key)
        if val and isinstance(val, str):
            parts.append(val)
            break
    key_ideas = payload.get("key_ideas")
    if isinstance(key_ideas, list):
        parts.extend(str(k) for k in key_ideas[:5] if k)
    tags = payload.get("topic_tags")
    if isinstance(tags, list):
        parts.append(" ".join(str(t) for t in tags[:10] if t))
    return " ".join(parts)[:4000]


def _build_qdrant_payload(
    summary_id: int,
    request_id: int,
    lang: str | None,
    json_payload: str | dict[str, Any] | None,
    user_scope: str,
    environment: str,
) -> dict[str, Any]:
    """Build the Qdrant point payload dict.

    Must be compatible with the payload schema produced by
    app.infrastructure.vector.metadata_builder.MetadataBuilder so that
    the existing query() path keeps working.
    """
    if isinstance(json_payload, str):
        try:
            payload = json.loads(json_payload)
        except (json.JSONDecodeError, ValueError):
            payload = {}
    else:
        payload = json_payload or {}

    metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
    return {
        "summary_id": summary_id,
        "request_id": request_id,
        "language": lang or "en",
        "user_scope": user_scope,
        "environment": environment,
        "title": metadata.get("title") or payload.get("title") or "",
        "url": metadata.get("url") or payload.get("url") or "",
        "source_type": payload.get("source_type") or "",
        "tldr": payload.get("tldr") or "",
        "topic_tags": payload.get("topic_tags") or [],
        "summary_250": payload.get("summary_250") or "",
    }


# ---------------------------------------------------------------------------
# Flow definition -- uses CocoIndex declarative API
# ---------------------------------------------------------------------------


def build_summaries_flow(
    *,
    collection_name: str,
    qdrant_url: str,
    qdrant_api_key: str | None,
    user_scope: str,
    environment: str,
    listen_channel: str = "ratatoskr_summaries_changed",
) -> Any:
    """Build and return the CocoIndex flow object.

    Called once during startup; the returned flow object is passed to
    CocoIndexRuntime which calls setup() and starts FlowLiveUpdater.

    All CocoIndex imports are lazy so the package is only required when
    cocoindex extra is installed (RATATOSKR_COCOINDEX_ENABLED=1).
    """
    try:
        import cocoindex  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "CocoIndex is not installed. Install with: pip install 'cocoindex>=1.0.3,<1.1'"
        ) from exc

    # Capture closure variables for the transform functions
    _user_scope = user_scope
    _environment = environment
    _collection_name = collection_name
    _qdrant_url = qdrant_url
    _qdrant_api_key = qdrant_api_key

    @cocoindex.flow_def(name="ratatoskr_summaries_to_qdrant")
    def summaries_to_qdrant(flow_builder: Any, data_scope: Any) -> None:
        """CocoIndex flow: incrementally sync summaries -> Qdrant."""
        data_scope["summaries"] = flow_builder.add_source(
            cocoindex.sources.Postgres(
                table_name="summaries",
                ordinal_field="updated_at",
                primary_key_fields=["id", "request_id"],
            )
        )

        qdrant_sink = data_scope.add_collector()

        with data_scope["summaries"].row() as row:
            summary_id = row["id"]
            request_id = row["request_id"]
            lang = row.get("lang")
            json_payload = row.get("json_payload")

            text = _extract_indexable_text(json_payload)
            if not text:
                return

            embedding = embed_text_sync(text, language=lang)
            point_id = summary_id_to_point_id(request_id, summary_id)
            payload = _build_qdrant_payload(
                summary_id=summary_id,
                request_id=request_id,
                lang=lang,
                json_payload=json_payload,
                user_scope=_user_scope,
                environment=_environment,
            )

            qdrant_sink.collect(
                id=point_id,
                vector=embedding,
                payload=payload,
            )

        qdrant_sink.export(
            "qdrant_points",
            cocoindex.targets.Qdrant(
                collection_name=_collection_name,
                url=_qdrant_url,
                api_key=_qdrant_api_key,
            ),
            primary_key_fields=["id"],
        )

    return summaries_to_qdrant
