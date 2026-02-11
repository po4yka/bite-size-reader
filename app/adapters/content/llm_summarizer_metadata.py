"""Metadata enrichment helper for LLM summarization."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

from app.core.async_utils import raise_if_cancelled
from app.core.json_utils import extract_json

logger = logging.getLogger(__name__)

_METADATA_FIELDS: tuple[str, ...] = (
    "title",
    "canonical_url",
    "domain",
    "author",
    "published_at",
    "last_updated",
)
_LLM_METADATA_FIELDS: tuple[str, ...] = ("title", "author", "published_at", "last_updated")
_FIRECRAWL_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "title": (
        "title",
        "og:title",
        "og_title",
        "meta_title",
        "twitter:title",
        "headline",
        "dc.title",
        "article:title",
    ),
    "canonical_url": (
        "canonical",
        "canonical_url",
        "og:url",
        "og_url",
        "url",
    ),
    "author": (
        "author",
        "article:author",
        "byline",
        "twitter:creator",
        "dc.creator",
        "creator",
    ),
    "published_at": (
        "article:published_time",
        "article:published",
        "article:publish_time",
        "article:publish_date",
        "datepublished",
        "date_published",
        "publish_date",
        "published",
        "pubdate",
    ),
    "last_updated": (
        "article:modified_time",
        "article:updated_time",
        "date_modified",
        "datemodified",
        "updated",
        "lastmod",
        "last_modified",
    ),
}


class LLMSummaryMetadataHelper:
    """Backfill missing metadata in summary payloads."""

    def __init__(
        self,
        *,
        request_repo: Any,
        crawl_result_repo: Any,
        openrouter: Any,
        workflow: Any,
        sem: Any,
        semantic_helper: Any,
    ) -> None:
        self._request_repo = request_repo
        self._crawl_result_repo = crawl_result_repo
        self._openrouter = openrouter
        self._workflow = workflow
        self._sem = sem
        self._semantic_helper = semantic_helper

    async def ensure_summary_metadata(
        self,
        summary: dict[str, Any],
        req_id: int,
        content_text: str,
        correlation_id: str | None,
        chosen_lang: str | None = None,
    ) -> dict[str, Any]:
        """Backfill critical metadata fields when the LLM leaves them empty."""
        metadata = summary.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            summary["metadata"] = metadata

        missing_fields: set[str] = {
            field for field in _METADATA_FIELDS if self._is_blank(metadata.get(field))
        }
        if not missing_fields:
            return summary

        firecrawl_flat = await self._load_firecrawl_metadata(req_id)
        if firecrawl_flat:
            filled_from_crawl = self._apply_firecrawl_metadata(
                metadata, missing_fields, firecrawl_flat, correlation_id
            )
            missing_fields -= filled_from_crawl

        request_row: dict[str, Any] | None = None
        try:
            request_row = await self._request_repo.async_get_request_by_id(req_id)
        except Exception as exc:
            raise_if_cancelled(exc)
            logger.exception(
                "request_lookup_failed", extra={"error": str(exc), "cid": correlation_id}
            )

        request_url: str | None = None
        if request_row:
            candidate_url = request_row.get("normalized_url") or request_row.get("input_url")
            if isinstance(candidate_url, str) and candidate_url.strip():
                request_url = candidate_url.strip()

        if "canonical_url" in missing_fields and request_url:
            metadata["canonical_url"] = request_url
            missing_fields.discard("canonical_url")
            logger.debug(
                "metadata_backfill",
                extra={"cid": correlation_id, "field": "canonical_url", "source": "request"},
            )

        if self._is_blank(metadata.get("domain")):
            domain_source = metadata.get("canonical_url") or request_url
            domain_value = self._extract_domain_from_url(domain_source)
            if domain_value:
                metadata["domain"] = domain_value
                missing_fields.discard("domain")
                logger.debug(
                    "metadata_backfill",
                    extra={"cid": correlation_id, "field": "domain", "source": "url"},
                )

        if "title" in missing_fields:
            heading_title = self._extract_heading_title(content_text)
            if heading_title:
                metadata["title"] = heading_title
                missing_fields.discard("title")
                logger.debug(
                    "metadata_backfill",
                    extra={"cid": correlation_id, "field": "title", "source": "heading"},
                )

        llm_targets = [field for field in _LLM_METADATA_FIELDS if field in missing_fields]
        if llm_targets and content_text.strip():
            generated = await self._generate_metadata_completion(
                content_text, llm_targets, req_id, correlation_id
            )
            for key, value in generated.items():
                if value and key in missing_fields:
                    metadata[key] = value
                    missing_fields.discard(key)

        if missing_fields:
            logger.info(
                "metadata_fields_still_missing",
                extra={"cid": correlation_id, "fields": sorted(missing_fields)},
            )

        # Enrich with RAG-optimized fields for retrieval
        return await self._semantic_helper.enrich_with_rag_fields(
            summary,
            content_text=content_text,
            chosen_lang=chosen_lang,
            req_id=req_id,
        )

    def _apply_firecrawl_metadata(
        self,
        metadata: dict[str, Any],
        missing_fields: set[str],
        flat_metadata: dict[str, str],
        correlation_id: str | None,
    ) -> set[str]:
        """Apply Firecrawl metadata values for missing fields."""
        filled: set[str] = set()
        for field in list(missing_fields):
            for alias in _FIRECRAWL_FIELD_ALIASES.get(field, ()):
                candidate = flat_metadata.get(alias)
                if self._is_blank(candidate):
                    continue
                metadata[field] = str(candidate).strip()
                filled.add(field)
                logger.debug(
                    "metadata_backfill",
                    extra={"cid": correlation_id, "field": field, "source": f"firecrawl:{alias}"},
                )
                break
        return filled

    async def _load_firecrawl_metadata(self, req_id: int) -> dict[str, str]:
        """Load and flatten Firecrawl metadata for a request."""
        try:
            crawl_row = await self._crawl_result_repo.async_get_crawl_result_by_request(req_id)
        except Exception as exc:
            raise_if_cancelled(exc)
            logger.exception("firecrawl_lookup_failed", extra={"error": str(exc)})
            return {}

        if not crawl_row:
            return {}

        parsed: Any = None
        metadata_raw = crawl_row.get("metadata_json")
        if metadata_raw:
            if isinstance(metadata_raw, dict):
                parsed = metadata_raw
            else:
                try:
                    parsed = json.loads(metadata_raw)
                except Exception as exc:
                    raise_if_cancelled(exc)
                    logger.warning("firecrawl_metadata_parse_error", extra={"error": str(exc)})

        if parsed is None:
            raw_payload = crawl_row.get("raw_response_json")
            if raw_payload:
                try:
                    payload = (
                        raw_payload if isinstance(raw_payload, dict) else json.loads(raw_payload)
                    )
                    if isinstance(payload, dict):
                        data_block = payload.get("data")
                        if isinstance(data_block, dict):
                            parsed = data_block.get("metadata") or data_block.get("meta")
                except Exception as exc:
                    raise_if_cancelled(exc)
                    logger.warning("firecrawl_raw_metadata_parse_error", extra={"error": str(exc)})

        if parsed is None:
            return {}

        flat: dict[str, str] = {}
        self._flatten_metadata_values(parsed, flat)
        return flat

    @classmethod
    def _flatten_metadata_values(cls, node: Any, collector: dict[str, str]) -> None:
        """Flatten nested metadata values into a single dict keyed by tag/property."""
        if node is None:
            return
        if isinstance(node, str | int | float):
            # Scalar without a key cannot be mapped reliably.
            return
        if isinstance(node, dict):
            key_hint = None
            for hint_key in ("property", "name", "itemprop", "rel", "key", "type"):
                if hint_key in node and isinstance(node[hint_key], str | int | float):
                    candidate = str(node[hint_key]).strip().lower()
                    if candidate:
                        key_hint = candidate
                        break

            value_hint = node.get("content") or node.get("value") or node.get("text")
            if key_hint and isinstance(value_hint, str | int | float):
                cleaned_value = str(value_hint).strip()
                if cleaned_value and key_hint not in collector:
                    collector[key_hint] = cleaned_value

            for key, value in node.items():
                normalized_key = str(key).strip().lower()
                if isinstance(value, str | int | float):
                    cleaned_child = str(value).strip()
                    if cleaned_child and normalized_key:
                        collector.setdefault(normalized_key, cleaned_child)
                else:
                    cls._flatten_metadata_values(value, collector)
            return

        if isinstance(node, list):
            for item in node:
                cls._flatten_metadata_values(item, collector)

    @staticmethod
    def _is_blank(value: Any) -> bool:
        """Return True when a metadata value is absent or empty."""
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        return not str(value).strip()

    @staticmethod
    def _extract_heading_title(content_text: str) -> str | None:
        """Derive a title from the first markdown heading or leading line."""
        if not content_text:
            return None
        match = re.search(r"^#{1,6}\s+(.+)$", content_text, flags=re.MULTILINE)
        if match:
            candidate = match.group(1).strip(" #\t")
            if candidate:
                return candidate

        lines = [line.strip() for line in content_text.splitlines() if line.strip()]
        if not lines:
            return None
        first_line = lines[0]
        if len(first_line) <= 140:
            return first_line
        return None

    async def _generate_metadata_completion(
        self,
        content_text: str,
        fields: list[str],
        req_id: int,
        correlation_id: str | None,
    ) -> dict[str, str]:
        """Ask the LLM to fill missing metadata fields when heuristics fail."""
        if not fields:
            return {}

        snippet = content_text[:6000].strip()
        if not snippet:
            return {}

        system_prompt = (
            "You extract article metadata and must respond with a strict JSON object. "
            "Do not add commentary. Use null when a field cannot be determined."
        )
        user_prompt = (
            "Provide the following metadata fields as JSON keys only: "
            f"{', '.join(fields)}.\n"
            "Base your answer on this article content.\n"
            "CONTENT START\n"
            f"{snippet}\n"
            "CONTENT END"
        )

        response_format = {
            "type": "json_object",
            "schema": {
                "name": "metadata_completion",
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {field: {"type": ["string", "null"]} for field in fields},
                    "required": list(fields),
                },
            },
        }

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            async with self._sem():
                llm = await self._openrouter.chat(
                    messages,
                    temperature=0.2,
                    max_tokens=512,
                    top_p=0.9,
                    request_id=req_id,
                    response_format=response_format,
                )
        except Exception as exc:
            raise_if_cancelled(exc)
            logger.warning(
                "metadata_completion_call_failed",
                extra={"cid": correlation_id, "error": str(exc)},
            )
            return {}

        await self._workflow.persist_llm_call(llm, req_id, correlation_id)

        if llm.status != "ok":
            logger.warning(
                "metadata_completion_failed",
                extra={"cid": correlation_id, "status": llm.status, "error": llm.error_text},
            )
            return {}

        parsed = self._parse_metadata_completion(llm.response_json, llm.response_text)
        if not isinstance(parsed, dict):
            logger.warning("metadata_completion_unparsed", extra={"cid": correlation_id})
            return {}

        cleaned: dict[str, str] = {}
        for field in fields:
            raw_value = parsed.get(field)
            if isinstance(raw_value, str) and raw_value.strip():
                cleaned[field] = raw_value.strip()

        if cleaned:
            logger.info(
                "metadata_completion_success",
                extra={"cid": correlation_id, "fields": list(cleaned.keys())},
            )

        return cleaned

    @staticmethod
    def _parse_metadata_completion(
        response_json: Any, response_text: str | None
    ) -> dict[str, Any] | None:
        """Parse metadata completion response into a dictionary."""
        candidate: dict[str, Any] | None = None
        if isinstance(response_json, dict):
            choices = response_json.get("choices") or []
            if choices:
                message = (choices[0] or {}).get("message") or {}
                parsed = message.get("parsed")
                if isinstance(parsed, dict):
                    candidate = parsed
                elif isinstance(parsed, str):
                    try:
                        loaded = json.loads(parsed)
                        if isinstance(loaded, dict):
                            candidate = loaded
                    except Exception:
                        candidate = None
                if candidate is None:
                    content = message.get("content")
                    if isinstance(content, str):
                        candidate = extract_json(content) or None
        if candidate is None and response_text:
            candidate = extract_json(response_text) or None
        return candidate

    @staticmethod
    def _extract_domain_from_url(url_value: Any) -> str | None:
        """Extract domain from a canonical URL."""
        if not url_value:
            return None
        try:
            parsed = urlparse(str(url_value))
            netloc = parsed.netloc or ""
            if not netloc and parsed.path:
                netloc = parsed.path.split("/")[0]
            netloc = netloc.strip().lower()
            netloc = netloc.removeprefix("www.")
            return netloc or None
        except Exception:
            logger.warning("domain_extraction_failed", exc_info=True)
            return None
