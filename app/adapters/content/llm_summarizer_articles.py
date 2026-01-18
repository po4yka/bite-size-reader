"""Custom article and translation helpers for LLM summarization."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.async_utils import raise_if_cancelled
from app.core.json_utils import extract_json
from app.core.lang import LANG_RU

logger = logging.getLogger(__name__)


class LLMArticleGenerator:
    """Generate long-form articles and translations from summary metadata."""

    def __init__(
        self,
        *,
        cfg: Any,
        openrouter: Any,
        workflow: Any,
        cache_helper: Any,
        sem: Any,
        select_max_tokens: Any,
        coerce_string_list: Any,
    ) -> None:
        self._cfg = cfg
        self._openrouter = openrouter
        self._workflow = workflow
        self._cache_helper = cache_helper
        self._sem = sem
        self._select_max_tokens = select_max_tokens
        self._coerce_string_list = coerce_string_list

    async def generate_custom_article(
        self,
        message: Any,
        *,
        chosen_lang: str,
        req_id: int,
        topics: list[str] | None,
        tags: list[str] | None,
        correlation_id: str | None,
        url_hash: str | None = None,
    ) -> dict[str, Any] | None:
        """Generate a standalone article based on extracted topics and tags."""
        topics = [str(t).strip() for t in (topics or []) if str(t).strip()]
        tags = [str(t).strip() for t in (tags or []) if str(t).strip()]

        topics_key = self._cache_helper.build_topics_cache_key(topics, tags)

        system_prompt = self._build_article_system_prompt(chosen_lang)
        user_prompt = self._build_article_user_prompt(topics, tags, chosen_lang)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response_formats: list[dict[str, Any]] = []
            primary_format = self._build_article_response_format()
            response_formats.append(primary_format)
            if primary_format.get("type") != "json_object":
                response_formats.append({"type": "json_object"})

            candidate_models: list[str] = [self._cfg.openrouter.model]
            candidate_models.extend(
                [
                    model
                    for model in self._cfg.openrouter.fallback_models
                    if model and model not in candidate_models
                ]
            )
            if url_hash and topics_key:
                for model_name in candidate_models:
                    cached = await self._cache_helper.get_cached_custom_article(
                        url_hash, chosen_lang, model_name, topics_key, correlation_id
                    )
                    if cached:
                        logger.info(
                            "custom_article_cache_hit",
                            extra={"cid": correlation_id, "model": model_name},
                        )
                        return cached

            max_tokens = self._select_max_tokens(" ".join(topics + tags))

            for model_name in candidate_models:
                for response_format in response_formats:
                    async with self._sem():
                        llm = await self._openrouter.chat(
                            messages,
                            temperature=self._cfg.openrouter.temperature,
                            max_tokens=max_tokens,
                            top_p=self._cfg.openrouter.top_p,
                            request_id=req_id,
                            response_format=response_format,
                            model_override=model_name,
                        )

                    await self._workflow.persist_llm_call(llm, req_id, correlation_id)

                    if llm.status != "ok":
                        structured_error = (llm.error_text or "") == "structured_output_parse_error"
                        logger.warning(
                            "custom_article_llm_error",
                            extra={
                                "cid": correlation_id,
                                "error": llm.error_text,
                                "model": model_name,
                                "response_format": response_format.get("type"),
                            },
                        )
                        if structured_error:
                            continue
                        return None

                    article = self._parse_article_response(llm.response_json, llm.response_text)
                    if not article:
                        logger.warning(
                            "custom_article_parse_failed",
                            extra={
                                "cid": correlation_id,
                                "model": model_name,
                                "response_format": response_format.get("type"),
                            },
                        )
                        continue
                    if url_hash and topics_key:
                        await self._cache_helper.write_custom_article_cache(
                            url_hash,
                            model_name,
                            chosen_lang,
                            topics_key,
                            article,
                        )
                    return article

            logger.warning("custom_article_generation_exhausted", extra={"cid": correlation_id})
            return None
        except Exception as exc:
            raise_if_cancelled(exc)
            logger.exception(
                "custom_article_generation_failed",
                extra={"cid": correlation_id, "error": str(exc)},
            )
            return None

    async def translate_summary_to_ru(
        self,
        summary: dict[str, Any],
        *,
        req_id: int,
        correlation_id: str | None = None,
        url_hash: str | None = None,
        source_lang: str | None = None,
    ) -> str | None:
        """Translate a shaped summary to fluent Russian for Telegram delivery."""
        source_lang = source_lang or summary.get("language") or "auto"

        candidate_models: list[str] = [self._cfg.openrouter.model]
        fallback_models = getattr(self._cfg.openrouter, "fallback_models", []) or []
        candidate_models.extend(
            [model for model in fallback_models if model and model not in candidate_models]
        )

        if url_hash:
            for model_name in candidate_models:
                cached = await self._cache_helper.get_cached_translation(
                    url_hash, source_lang, model_name, correlation_id
                )
                if cached:
                    logger.info(
                        "translation_cache_hit",
                        extra={"cid": correlation_id, "model": model_name},
                    )
                    return cached

        summary_json = json.dumps(summary, ensure_ascii=False, indent=2)

        system_prompt = (
            "Ты опытный редактор и переводчик. Получишь структурированное резюме (JSON). "
            "Передай тот же смысл на русском в сжатом виде: 2–3 коротких абзаца и, если уместно, "
            "несколько лаконичных bullet-пунктов. Не возвращай JSON, не используй Markdown-разметку "
            "или кодовые блоки. Сохраняй факты, числа и имена без искажений."
        )
        user_prompt = (
            "Преобразуй резюме ниже в связный русский текст для Telegram. "
            "Сделай адаптированный перевод (не дословный), сохрани ключевые факты, тон и цифры. "
            "Избегай префиксов вроде 'Translation:' и любых служебных пометок.\n\n"
            f"Резюме:\n{summary_json}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        max_tokens = 900

        for model_name in candidate_models:
            try:
                async with self._sem():
                    llm = await self._openrouter.chat(
                        messages,
                        temperature=self._cfg.openrouter.temperature,
                        max_tokens=max_tokens,
                        top_p=self._cfg.openrouter.top_p,
                        model_override=model_name,
                        request_id=req_id,
                    )

                await self._workflow.persist_llm_call(llm, req_id, correlation_id)

                if llm.status != "ok":
                    logger.warning(
                        "ru_translation_llm_error",
                        extra={
                            "cid": correlation_id,
                            "error": llm.error_text,
                            "model": model_name,
                        },
                    )
                    continue

                candidate = (llm.response_text or "").strip()
                if candidate:
                    if url_hash:
                        await self._cache_helper.write_translation_cache(
                            url_hash, model_name, source_lang, candidate
                        )
                    return candidate

                logger.warning(
                    "ru_translation_empty_text",
                    extra={"cid": correlation_id, "model": model_name},
                )
            except Exception as exc:
                raise_if_cancelled(exc)
                logger.exception(
                    "ru_translation_call_failed",
                    extra={"cid": correlation_id, "model": model_name, "error": str(exc)},
                )
                continue

        logger.warning("ru_translation_exhausted", extra={"cid": correlation_id})
        return None

    def _build_article_system_prompt(self, lang: str) -> str:
        if lang == LANG_RU:
            return (
                "Ты ведущий редактор-аналитик. На основе тем и тэгов подготовь"
                " обстоятельную самостоятельную статью, объясняя контекст,"
                " ключевые события, последствия и перспективы. Поддерживай"
                " связное повествование, используй подзаголовок, H2/H3-разделы,"
                " фактические детали и списки, когда уместно. Верни строго JSON"
                " по заданной схеме."
            )
        return (
            "You are a senior long-form editor and analyst. Using the provided topics"
            " and tags, craft a comprehensive standalone article that explains"
            " context, key developments, implications, and outlook. Maintain a clear"
            " narrative, include a short subtitle, structured H2/H3 sections,"
            " concrete details, and bullet lists when helpful. Return strictly as"
            " JSON per the schema."
        )

    def _build_article_user_prompt(self, topics: list[str], tags: list[str], lang: str) -> str:
        lang_label = "Russian" if lang == LANG_RU else "English"
        topics_text = "\n".join(f"- {t}" for t in topics[:12]) or "- (none)"
        tags_text = "\n".join(f"- {t}" for t in tags[:12]) or "- (none)"
        return (
            f"Respond in {lang_label}."
            "\nReturn JSON only with exactly these keys (no extras):"
            '\n{\n  "title": string,\n  "subtitle": string | null,\n  "article_markdown": string,\n  "highlights": [string],\n'
            '"suggested_sources": [string]\n}'
            "\nGuidelines:"
            "\n- `article_markdown` must be a detailed 600-900 word Markdown article with"
            " an engaging introduction, at least four `##` sections, optional `###`"
            " subsections, and short paragraphs (2-3 sentences)."
            "\n- Cover background/context, the current landscape, key drivers or"
            " challenges, stakeholder perspectives, quantitative examples or"
            " milestones, and forward-looking implications or recommendations."
            "\n- Weave provided topics and tags naturally as keywords and explain the"
            " relationships between them."
            "\n- Close with a concise conclusion summarizing takeaways."
            "\n- Provide 5-7 highlight bullet points, each under 160 characters and"
            " capturing distinct insights."
            "\n- Provide 4-6 reputable suggested sources (URLs or publication names);"
            " avoid duplicates and low-quality outlets."
            "\n- Strings may exceed 400 characters when necessary, but keep highlight"
            " and source entries succinct. Use empty arrays when you truly lack"
            " items, but never omit required keys."
            "\n\nTOPICS:\n"
            f"{topics_text}"
            "\n\nTAGS:\n"
            f"{tags_text}\n"
        )

    def _build_article_response_format(self) -> dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "custom_article_schema",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string"},
                        "subtitle": {"type": ["string", "null"]},
                        "article_markdown": {"type": "string"},
                        "highlights": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "suggested_sources": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["title", "article_markdown"],
                },
            },
        }

    def _parse_article_response(
        self, response_json: Any, response_text: str | None
    ) -> dict[str, Any] | None:
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
                        candidate = loaded if isinstance(loaded, dict) else None
                    except Exception:
                        candidate = None
                if candidate is None:
                    content = message.get("content")
                    if isinstance(content, str):
                        candidate = extract_json(content) or None
        if candidate is None and response_text:
            textracted = extract_json(response_text)
            if isinstance(textracted, dict):
                candidate = textracted

        if isinstance(candidate, dict):
            article_payload = candidate.get("article")
            if isinstance(article_payload, dict):
                merged: dict[str, Any] = {**candidate, **article_payload}
                candidate = merged

            # Normalise common body field variants before attempting to coerce sections
            body_keys_precedence: tuple[str, ...] = (
                "article_markdown",
                "articleBody",
                "articleBodyMarkdown",
                "articleMarkdown",
                "body_markdown",
                "bodyMarkdown",
                "body",
                "markdown",
                "content_markdown",
            )
            if "article_markdown" not in candidate:
                for key in body_keys_precedence:
                    if key in candidate and candidate.get(key):
                        candidate["article_markdown"] = candidate.get(key)
                        break

            # Join sections when available, accounting for both explicit section
            # containers and when the body itself is a list/dict structure.
            if not candidate.get("article_markdown"):
                for section_key in ("article_sections", "sections"):
                    sections = candidate.get(section_key)
                    if not isinstance(sections, list):
                        continue
                    section_text = self._coerce_section_list(sections)
                    if section_text:
                        candidate["article_markdown"] = section_text
                        break

            article_markdown_value = candidate.get("article_markdown")
            if isinstance(article_markdown_value, list):
                coerced = self._coerce_section_list(article_markdown_value)
                if coerced:
                    candidate["article_markdown"] = coerced
            elif isinstance(article_markdown_value, dict):
                coerced = self._coerce_section_dict(article_markdown_value)
                if coerced:
                    candidate["article_markdown"] = coerced

        if not isinstance(candidate, dict):
            return None
        title = str(
            candidate.get("title")
            or candidate.get("headline")
            or candidate.get("article_title")
            or ""
        ).strip()
        body = str(
            candidate.get("article_markdown")
            or candidate.get("body")
            or candidate.get("body_markdown")
            or candidate.get("markdown")
            or ""
        ).strip()
        if not title or not body:
            return None

        for list_key in ("highlights", "suggested_sources"):
            coerced_list = self._coerce_string_list(candidate.get(list_key))
            candidate[list_key] = coerced_list

        return candidate

    def _coerce_section_list(self, sections: list[Any]) -> str | None:
        """Convert a list of section payloads into Markdown text."""
        section_builder: list[str] = []
        for section in sections:
            if isinstance(section, str):
                text = section.strip()
                if text:
                    section_builder.append(text)
                continue

            if isinstance(section, dict):
                coerced = self._coerce_section_dict(section)
                if coerced:
                    section_builder.append(coerced)
                continue

            if isinstance(section, list):
                nested = self._coerce_section_list(section)
                if nested:
                    section_builder.append(nested)

        if not section_builder:
            return None
        return "\n\n".join(section_builder)

    def _coerce_section_dict(self, section: dict[str, Any]) -> str | None:
        """Coerce a dict-style section into Markdown."""
        if "sections" in section and isinstance(section["sections"], list):
            return self._coerce_section_list(section["sections"])

        heading = str(
            section.get("heading") or section.get("title") or section.get("section_title") or ""
        ).strip()
        body_text = section.get("markdown")
        if not body_text:
            body_text = (
                section.get("body")
                or section.get("content")
                or section.get("text")
                or section.get("paragraph")
            )
        if isinstance(body_text, list):
            body_text = self._coerce_section_list(body_text)
        else:
            body_text = str(body_text or "").strip()

        parts: list[str] = []
        if heading:
            parts.append(f"## {heading}")
        if body_text:
            parts.append(str(body_text))

        if not parts:
            return None
        return "\n\n".join(parts)
