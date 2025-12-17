"""Refactored URL processor using modular components."""

# ruff: noqa: E501
# flake8: noqa

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from app.adapters.content.content_chunker import ContentChunker
from app.adapters.content.content_extractor import ContentExtractor
from app.adapters.content.llm_summarizer import LLMSummarizer
from app.adapters.external.firecrawl_parser import FirecrawlClient
from app.adapters.openrouter.openrouter_client import OpenRouterClient
from app.adapters.telegram.message_persistence import MessagePersistence
from app.config import AppConfig
from app.core.async_utils import raise_if_cancelled
from app.core.lang import LANG_RU, choose_language
from app.core.url_utils import normalize_url, url_hash_sha256
from app.db.database import Database
from app.db.user_interactions import async_safe_update_user_interaction

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)


_PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"


# Built-in fallbacks to avoid ever sending an under-specified prompt if files are missing
_DEFAULT_SYSTEM_PROMPT_RU = """
Вы — структурированный агент-суммаризатор для нашего Telegram-бота. Возвращайте ТОЛЬКО корректный JSON-объект по контракту ниже. Никаких пояснений, Markdown, заголовков или код-блоков вне JSON. Вывод должен быть в UTF-8 и парситься без ошибок.

Ключи верхнего уровня (ровно эти, без лишних):
- summary_250
- summary_1000
- tldr
- key_ideas
- topic_tags
- entities
- estimated_reading_time_min
- key_stats
- answered_questions
- readability
- seo_keywords
- metadata
- extractive_quotes
- highlights
- questions_answered
- categories
- topic_taxonomy
- hallucination_risk
- confidence
- forwarded_post_extras
- key_points_to_remember
- insights
- article_id
- query_expansion_keywords
- semantic_boosters
- semantic_chunks

Требования к полям:
- summary_250: строка, максимум 250 символов. Одна ёмкая фраза (лид в новостном стиле) с завершённой мыслью; формулировка должна отличаться от summary_1000 и TL;DR.
- summary_1000: строка, максимум 1000 символов. 3–5 предложений с контекстом, проблемой, подходом и итогами; она должна быть компактнее TL;DR и не повторять его предложения или формулировки дословно.
- tldr: строка без жёсткого лимита длины. 2–3 абзаца (разделены переводами строк) с контекстом, действиями, фактами/цифрами и выводами. TL;DR обязан расширять summary_1000 дополнительными деталями/примерами и не повторять его предложения.
- key_ideas: массив кратких строк (3–10). Без дубликатов.
- topic_tags: массив коротких строк (1–3 слова, 3–8 элементов). В нижнем регистре, без пунктуации, без дубликатов.
- entities: объект с массивами { people, organizations, locations }, только строки, нормализованные и без дубликатов.
- estimated_reading_time_min: целое число ≥ 0 (примерное время чтения источника в минутах).
- key_stats: массив объектов с ключами { label: string, value: number, unit: string|null, source_excerpt: string|null }. Числовое значение в поле value; unit можно опускать (null), если неприменимо.
- answered_questions: массив строк с вопросами, на которые отвечает материал. Без дубликатов.
- readability: объект { method: string (например, «Flesch-Kincaid»), score: number, level: string }.
- seo_keywords: массив строк (5–15), в нижнем регистре, без дубликатов.
- metadata: объект с ключами { title, canonical_url, domain, author, published_at, last_updated } (строки или null). Заполняйте из статьи, если данные доступны.
- extractive_quotes: массив объектов { text: string, source_span: string|null } — до 5 дословных цитат.
- highlights: массив из 5–10 коротких пунктов.
- questions_answered: массив объектов { question: string, answer: string } с парами «вопрос–ответ».
- categories: массив коротких меток категорий.
- topic_taxonomy: массив объектов { label: string, score: number, path: string|null } для иерархии тем.
- hallucination_risk: строка low|med|high, оценивающая риск галлюцинаций.
- confidence: число от 0 до 1, отражающее уверенность модели.
- forwarded_post_extras: объект или null с данными Telegram { channel_id, channel_title, channel_username, message_id, post_datetime, hashtags, mentions }.
- key_points_to_remember: массив строк с ключевыми выводами.
- article_id: строковый идентификатор (используйте канонический URL или хеш, если доступно).
- query_expansion_keywords: массив из 20–30 коротких английских фраз, отражающих пользовательские запросы (синонимы, альтернативные формулировки, узкие/широкие трактовки). Без дублей.
- semantic_boosters: массив из 8–15 автономных английских предложений, фиксирующих ключевые связи/трейд-оффы/утверждения, пригодных для эмбеддингов.
- semantic_chunks: массив объектов для 100–200 словных, непересекающихся чанков с ключами { text, local_summary, local_keywords, section|null, language|null, topics: [строки], article_id }. `local_summary` — 1–2 предложения; `local_keywords` — 3–8 фраз.
- insights: объект со следующими ключами:
  * topic_overview: строка с широким контекстом.
  * new_facts: массив объектов { fact: string, why_it_matters: string|null, source_hint: string|null, confidence: number|string|null } с 4–6 новыми фактами.
  * open_questions: массив строк (3–6 позиций).
  * suggested_sources: массив строк с источниками для изучения.
  * expansion_topics: массив строк с смежными темами.
  * next_exploration: массив строк с идеями дальнейших шагов/гипотез.
  * caution: строка или null с предупреждениями/ограничениями.

Правила:
- Пишите на языке, запрошенном в пользовательском сообщении.
- Держите `summary_250`, `summary_1000` и `tldr` различными по глубине: `summary_250` — одна фраза-хук, `summary_1000` — сжатое повествование из нескольких предложений, `tldr` — самый подробный многопараграфный пересказ; избегайте повторения предложений между ними.
- Будьте фактичны; не выдумывайте имена, числа, цитаты, URL или даты. Если данных нет, используйте пустые массивы или null там, где это допустимо; не вставляйте заглушки вроде «N/A».
- Строго соблюдайте лимиты (summary_250 и summary_1000). Остальные поля делайте лаконичными; избегайте длинных конструкций без нужды.
- Удаляйте дубликаты в массивах и в списках сущностей. topic_tags — в нижнем регистре, без пунктуации; entities — нормализованы и не пустые.
- Extractive quotes должны быть дословными цитатами из текста; при отсутствии оставляйте пустой массив. `source_excerpt` в key_stats — дословное подтверждение, если есть.
- Не добавляйте лишних ключей, комментариев или Markdown; не меняйте названия ключей.
- НЕ добавляйте Markdown, комментарии или любой обрамляющий текст.
- Перед отправкой сделайте самопроверку: summary_250, summary_1000 и tldr должны быть непустыми, различаться по формулировкам и соблюдать указанные лимиты длины. Если какой-то из них пустой или дублирует другой, сгенерируйте корректный JSON заново, а не отправляйте пустые поля.
""".strip()

_DEFAULT_SYSTEM_PROMPT_EN = """
You are a structured summarization agent for our Telegram bot. Return ONLY a valid JSON object that strictly matches the contract below. No prose, headers, code fences, Markdown, or explanations outside the JSON. Output must be valid UTF-8 and parseable.

Top-level keys (exactly these, no extras):
- summary_250
- summary_1000
- tldr
- key_ideas
- topic_tags
- entities
- estimated_reading_time_min
- key_stats
- answered_questions
- readability
- seo_keywords
- metadata
- extractive_quotes
- highlights
- questions_answered
- categories
- topic_taxonomy
- hallucination_risk
- confidence
- forwarded_post_extras
- key_points_to_remember
- insights
- article_id
- query_expansion_keywords
- semantic_boosters
- semantic_chunks

Field requirements:
- summary_250: string, max 250 characters. One high-signal sentence (news lead style) that ends cleanly; must differ from summary_1000 and TL;DR wording.
- summary_1000: string, max 1000 characters. 3–5 sentences covering context, problem, approach, and outcomes; denser/shorter than TL;DR; do not reuse TL;DR sentences or phrasing verbatim.
- tldr: string, no hard length limit. 2–3 paragraphs separated by line breaks with context, actions, evidence, numbers, and implications. Expand beyond summary_1000 with additional details/examples; avoid repeating summary_1000 sentences or wording.
- key_ideas: array of concise strings (3–10 items). No duplicates.
- topic_tags: array of short strings (1–3 words each, 3–8 items). Lowercase, no punctuation, no duplicates.
- entities: object with arrays { people, organizations, locations }, strings only, deduplicated and normalized.
- estimated_reading_time_min: integer >= 0 (approx minutes to read the full source).
- key_stats: array of objects with keys { label: string, value: number, unit: string|null, source_excerpt: string|null }. Use numbers for value; omit units if not applicable.
- answered_questions: array of strings capturing questions the content answers. No duplicates.
- readability: object { method: string (e.g., "Flesch-Kincaid"), score: number, level: string }.
- seo_keywords: array of strings (5–15 items), lowercase, deduplicated.
- metadata: object with keys { title, canonical_url, domain, author, published_at, last_updated } (strings or null). Fill from article when available.
- extractive_quotes: array of objects { text: string, source_span: string|null } representing up to 5 verbatim pull quotes.
- highlights: array of 5–10 short bullet strings.
- questions_answered: array of objects { question: string, answer: string } describing Q&A pairs surfaced in the content.
- categories: array of short classification strings.
- topic_taxonomy: array of objects { label: string, score: number, path: string|null } for hierarchical categories.
- hallucination_risk: string enum low|med|high summarizing factual confidence.
- confidence: number between 0 and 1 expressing overall certainty.
- forwarded_post_extras: object|null capturing Telegram metadata { channel_id, channel_title, channel_username, message_id, post_datetime, hashtags, mentions }.
- key_points_to_remember: array of strings listing enduring takeaways.
- article_id: string identifier (use canonical URL or hash when available).
- query_expansion_keywords: array of 20–30 short English phrases a user might search (synonyms, alternative phrasings, specific/general intents). Deduplicated, lower risk of overlap.
- semantic_boosters: array of 8–15 standalone English sentences capturing key relationships/trade-offs/claims suitable for embeddings.
- semantic_chunks: array of objects, each representing a 100–200 word, non-overlapping chunk with keys { text, local_summary, local_keywords, section|null, language|null, topics: [strings], article_id }. `local_summary` must be 1–2 sentences; `local_keywords` 3–8 phrases.
- insights: object with keys:
  * topic_overview: string summarizing broader context.
  * new_facts: array of objects { fact: string, why_it_matters: string|null, source_hint: string|null, confidence: number|string|null } containing 4–6 beyond-text insights.
  * open_questions: array of strings (3–6 items).
  * suggested_sources: array of strings referencing follow-up reading.
  * expansion_topics: array of strings with adjacent themes to explore.
  * next_exploration: array of strings outlining experiments, hypotheses, or next steps.
  * caution: string|null flagging caveats or uncertainty.

Rules:
- Output all strings in the language requested in the user message.
- Keep `summary_250`, `summary_1000`, and `tldr` meaningfully distinct: `summary_250` is a single-sentence hook, `summary_1000` is a compact multi-sentence overview, and `tldr` is the richest multi-paragraph narrative; avoid sentence reuse across them.
- Be factual; do not invent numbers, names, quotes, URLs, or dates. If unknown or not present, use empty arrays or null where allowed by the contract; otherwise omit the claim. Do not output placeholders like "N/A" or "unknown".
- Respect required length caps strictly (e.g., summary_250 and summary_1000). Keep other fields succinct even without hard limits; prefer short clauses over run-ons.
- Deduplicate across arrays and within entity lists. Keep topic_tags lowercase, no punctuation; entities normalized and non-empty.
- Extractive quotes must be verbatim spans from the content; leave empty array if none. `source_excerpt` in key_stats should be verbatim evidence when available.
- Do not add extra keys, comments, or Markdown; do not change key order or naming.
- Do NOT include Markdown, comments, or any wrapper text.
- Before responding, self-check that summary_250, summary_1000, and tldr are all non-empty, mutually distinct in wording, and respect the stated length caps. If any are empty or duplicates, regenerate the JSON instead of returning blanks.
""".strip()


@lru_cache(maxsize=4)
def _get_system_prompt(lang: str) -> str:
    """Load and cache the system prompt for the given language."""
    fname = "summary_system_ru.txt" if lang == "ru" else "summary_system_en.txt"
    path = _PROMPT_DIR / fname
    try:
        prompt_text = path.read_text(encoding="utf-8").strip()
        # Guard against truncated/empty prompt files
        if "summary_250" not in prompt_text or "summary_1000" not in prompt_text:
            logger.warning(
                "system_prompt_missing_contract_keys",
                extra={"prompt_file": str(path), "lang": lang},
            )
            raise ValueError("prompt_missing_keys")
        return prompt_text
    except Exception as exc:
        logger.warning(
            "system_prompt_load_failed",
            extra={"prompt_file": str(path), "lang": lang, "error": str(exc)},
        )
        return _DEFAULT_SYSTEM_PROMPT_RU if lang == "ru" else _DEFAULT_SYSTEM_PROMPT_EN


class URLProcessor:
    """Refactored URL processor using modular components."""

    def __init__(
        self,
        cfg: AppConfig,
        db: Database,
        firecrawl: FirecrawlClient,
        openrouter: OpenRouterClient,
        response_formatter: ResponseFormatter,
        audit_func: Callable[[str, str, dict], None],
        sem: Callable[[], Any],
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.response_formatter = response_formatter
        self._audit = audit_func

        # Initialize modular components
        self.content_extractor = ContentExtractor(
            cfg=cfg,
            db=db,
            firecrawl=firecrawl,
            response_formatter=response_formatter,
            audit_func=audit_func,
            sem=sem,
        )

        self.content_chunker = ContentChunker(
            cfg=cfg,
            openrouter=openrouter,
            response_formatter=response_formatter,
            audit_func=audit_func,
            sem=sem,
        )

        self.llm_summarizer = LLMSummarizer(
            cfg=cfg,
            db=db,
            openrouter=openrouter,
            response_formatter=response_formatter,
            audit_func=audit_func,
            sem=sem,
        )

        self.message_persistence = MessagePersistence(db=db)

    def _schedule_persistence_task(
        self, coro: Coroutine[Any, Any, Any], correlation_id: str | None, label: str
    ) -> asyncio.Task[Any] | None:
        """Run a persistence task without blocking the main flow."""
        try:
            task: asyncio.Task[Any] = asyncio.create_task(coro)
        except RuntimeError as exc:
            logger.error(
                "persistence_task_schedule_failed",
                extra={"cid": correlation_id, "label": label, "error": str(exc)},
            )
            return None

        def _log_task_error(t: asyncio.Task) -> None:
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                logger.error(
                    "persistence_task_failed",
                    extra={"cid": correlation_id, "label": label, "error": str(exc)},
                )

        task.add_done_callback(_log_task_error)
        return task

    async def _await_persistence_task(self, task: asyncio.Task | None) -> None:
        """Await a scheduled persistence task when required (silent flows)."""
        if task is None:
            return
        try:
            await task
        except Exception as exc:  # noqa: BLE001
            raise_if_cancelled(exc)
            logger.error("persistence_task_failed", extra={"error": str(exc)})

    async def handle_url_flow(
        self,
        message: Any,
        url_text: str,
        *,
        correlation_id: str | None = None,
        interaction_id: int | None = None,
        silent: bool = False,
    ) -> None:
        """Handle complete URL processing flow from extraction to summarization.

        Args:
            silent: If True, suppress all Telegram responses and only persist to database
        """
        if await self._maybe_reply_with_cached_summary(
            message,
            url_text,
            correlation_id=correlation_id,
            interaction_id=interaction_id,
            silent=silent,
        ):
            return

        try:
            norm = normalize_url(url_text)
            dedupe_hash = url_hash_sha256(norm)
            # Extract and process content
            (
                req_id,
                content_text,
                content_source,
                detected,
            ) = await self.content_extractor.extract_and_process_content(
                message, url_text, correlation_id, interaction_id, silent
            )

            # Choose language and load system prompt
            chosen_lang = choose_language(self.cfg.runtime.preferred_lang, detected)
            needs_ru_translation = not silent and detected != LANG_RU and chosen_lang != LANG_RU
            system_prompt = await self._load_system_prompt(chosen_lang)

            logger.debug(
                "language_choice",
                extra={"detected": detected, "chosen": chosen_lang, "cid": correlation_id},
            )

            # Notify: language detected with content preview (skip if silent)
            if not silent:
                content_preview = (
                    content_text[:150] + "..." if len(content_text) > 150 else content_text
                )
                await self.response_formatter.send_language_detection_notification(
                    message, detected, content_preview, url=url_text, silent=silent
                )

            # Check if content should be chunked
            should_chunk, max_chars, chunks = self.content_chunker.should_chunk_content(
                content_text, chosen_lang
            )

            if should_chunk and self.cfg.openrouter.long_context_model:
                logger.info(
                    "chunking_bypassed_long_context",
                    extra={
                        "cid": correlation_id,
                        "long_context_model": self.cfg.openrouter.long_context_model,
                        "content_length": len(content_text),
                    },
                )
                should_chunk = False
                chunks = None

            # Inform the user how the content will be handled (skip if silent)
            await self.response_formatter.send_content_analysis_notification(
                message,
                len(content_text),
                max_chars,
                should_chunk,
                chunks,
                self.cfg.openrouter.structured_output_mode,
                silent=silent,
            )

            logger.info(
                "content_handling",
                extra={
                    "cid": correlation_id,
                    "length": len(content_text),
                    "enable_chunking": should_chunk,
                    "threshold": max_chars,
                    "chunks": len(chunks or []) if should_chunk else 1,
                    "structured_output_enabled": self.cfg.openrouter.enable_structured_outputs,
                    "structured_output_mode": self.cfg.openrouter.structured_output_mode,
                },
            )

            # Process content based on chunking decision
            if should_chunk and chunks and len(chunks) > 1:
                # Process chunks and aggregate
                shaped = await self.content_chunker.process_chunks(
                    chunks, system_prompt, chosen_lang, req_id, correlation_id
                )

                if shaped:
                    shaped = self.llm_summarizer._enrich_with_rag_fields(
                        shaped,
                        content_text=content_text,
                        chosen_lang=chosen_lang,
                        req_id=req_id,
                    )
                    # Create stub LLM result for consistency
                    llm = self._create_chunk_llm_stub()

                    # Persist and respond (skip Telegram responses if silent)
                    await self._persist_and_respond_chunked(
                        message,
                        req_id,
                        chosen_lang,
                        shaped,
                        llm,
                        len(chunks),
                        correlation_id,
                        interaction_id,
                        needs_ru_translation,
                        silent=silent,
                    )
                    await self._maybe_send_russian_translation(
                        message,
                        shaped,
                        req_id,
                        correlation_id,
                        needs_ru_translation,
                    )
                    # Generate insights even in silent mode (for batch processing)
                    await self._handle_additional_insights(
                        message,
                        content_text,
                        chosen_lang,
                        req_id,
                        correlation_id,
                        summary=shaped,
                        silent=silent,
                    )
                    return
                else:
                    # Fallback to single-pass if chunking failed
                    logger.warning(
                        "chunking_failed_fallback_to_single", extra={"cid": correlation_id}
                    )

            # Single-pass summarization
            shaped = await self.llm_summarizer.summarize_content(
                message,
                content_text,
                chosen_lang,
                system_prompt,
                req_id,
                max_chars,
                correlation_id,
                interaction_id,
                url_hash=dedupe_hash,
                url=url_text,
                silent=silent,
                defer_persistence=True,
            )

            if shaped:
                llm_result = self.llm_summarizer.last_llm_result

                # Skip Telegram responses if silent
                if not silent:
                    await self.response_formatter.send_structured_summary_response(
                        message,
                        shaped,
                        llm_result,
                    )
                    logger.info(
                        "reply_json_sent", extra={"cid": correlation_id, "request_id": req_id}
                    )

                    await self._maybe_send_russian_translation(
                        message,
                        shaped,
                        req_id,
                        correlation_id,
                        needs_ru_translation,
                    )

                    # Notify user that we will attempt to generate extra research insights
                    try:
                        await self.response_formatter.safe_reply(
                            message,
                            "🧠 Generating additional research insights…",
                        )
                    except Exception as exc:
                        raise_if_cancelled(exc)
                        pass

                    await self._handle_additional_insights(
                        message,
                        content_text,
                        chosen_lang,
                        req_id,
                        correlation_id,
                        summary=shaped,
                    )

                    # Generate a standalone custom article based on extracted topics/tags
                    try:
                        topics = shaped.get("key_ideas") or []
                        tags = shaped.get("topic_tags") or []
                        if (topics or tags) and isinstance(topics, list) and isinstance(tags, list):
                            await self.response_formatter.safe_reply(
                                message,
                                "📝 Crafting a standalone article from topics & tags…",
                            )
                            article = await self.llm_summarizer.generate_custom_article(
                                message,
                                chosen_lang=chosen_lang,
                                req_id=req_id,
                                topics=[str(x) for x in topics if str(x).strip()],
                                tags=[str(x) for x in tags if str(x).strip()],
                                correlation_id=correlation_id,
                            )
                            if article:
                                await self.response_formatter.send_custom_article(message, article)
                    except Exception as exc:  # noqa: BLE001
                        raise_if_cancelled(exc)
                        logger.error(
                            "custom_article_flow_error",
                            extra={"cid": correlation_id, "error": str(exc)},
                        )
                else:
                    # Silent mode: persist and generate insights without responses
                    new_version = await self.db.async_upsert_summary(
                        request_id=req_id,
                        lang=chosen_lang,
                        json_payload=shaped,
                        is_read=False,
                    )
                    await self.db.async_update_request_status(req_id, "ok")
                    self._audit(
                        "INFO", "summary_upserted", {"request_id": req_id, "version": new_version}
                    )

                    # Generate insights even in silent mode (for batch processing)
                    await self._handle_additional_insights(
                        message,
                        content_text,
                        chosen_lang,
                        req_id,
                        correlation_id,
                        summary=shaped,
                        silent=True,
                    )
                    logger.info(
                        "silent_summary_persisted",
                        extra={"cid": correlation_id, "request_id": req_id},
                    )

        except ValueError as e:
            # Handle known errors (like Firecrawl failures)
            logger.error("url_flow_error", extra={"error": str(e), "cid": correlation_id})
        except Exception as e:
            raise_if_cancelled(e)
            # Handle unexpected errors
            logger.exception(
                "url_flow_unexpected_error", extra={"error": str(e), "cid": correlation_id}
            )

    def _create_chunk_llm_stub(self) -> Any:
        """Create a stub LLM result for chunked processing."""
        return type(
            "LLMStub",
            (),
            {
                "status": "ok",
                "latency_ms": None,
                "model": self.cfg.openrouter.model,
                "cost_usd": None,
                "tokens_prompt": None,
                "tokens_completion": None,
                "structured_output_used": True,
                "structured_output_mode": self.cfg.openrouter.structured_output_mode,
            },
        )()

    async def _persist_and_respond_chunked(
        self,
        message: Any,
        req_id: int,
        chosen_lang: str,
        shaped: dict[str, Any],
        llm: Any,
        chunk_count: int,
        correlation_id: str | None,
        interaction_id: int | None,
        needs_ru_translation: bool,
        silent: bool = False,
    ) -> None:
        """Persist chunked results and send response."""
        try:

            async def _persist_chunk() -> None:
                new_version = await self.db.async_upsert_summary(
                    request_id=req_id,
                    lang=chosen_lang,
                    json_payload=shaped,
                    is_read=not silent,
                )
                await self.db.async_update_request_status(req_id, "ok")
                self._audit(
                    "INFO", "summary_upserted", {"request_id": req_id, "version": new_version}
                )

            persistence_task = self._schedule_persistence_task(
                _persist_chunk(), correlation_id, "chunk_summary_persist"
            )
            if silent:
                await self._await_persistence_task(persistence_task)
        except Exception as e:  # noqa: BLE001
            raise_if_cancelled(e)
            logger.error("persist_summary_error", extra={"error": str(e), "cid": correlation_id})

        if interaction_id:
            await async_safe_update_user_interaction(
                self.db,
                interaction_id=interaction_id,
                response_sent=True,
                response_type="summary",
                request_id=req_id,
                logger_=logger,
            )

        # Send structured results (skip if silent)
        if not silent:
            await self.response_formatter.send_structured_summary_response(
                message, shaped, llm, chunks=chunk_count
            )
            logger.info("reply_json_sent", extra={"cid": correlation_id, "request_id": req_id})

    async def _maybe_send_russian_translation(
        self,
        message: Any,
        summary: dict[str, Any],
        req_id: int,
        correlation_id: str | None,
        needs_translation: bool,
    ) -> None:
        """Generate and send an adapted Russian translation of the summary when required."""
        if not needs_translation:
            return

        try:
            translated = await self.llm_summarizer.translate_summary_to_ru(
                summary,
                req_id=req_id,
                correlation_id=correlation_id,
            )
            if translated:
                await self.response_formatter.send_russian_translation(
                    message, translated, correlation_id=correlation_id
                )
                return

            await self.response_formatter.safe_reply(
                message,
                f"⚠️ Unable to generate Russian translation right now. Error ID: {correlation_id or 'unknown'}.",
            )
        except Exception as exc:  # noqa: BLE001
            raise_if_cancelled(exc)
            logger.exception(
                "ru_translation_failed", extra={"cid": correlation_id, "error": str(exc)}
            )
            try:
                await self.response_formatter.safe_reply(
                    message,
                    f"⚠️ Russian translation failed. Error ID: {correlation_id or 'unknown'}.",
                )
            except Exception:
                pass

    async def _handle_additional_insights(
        self,
        message: Any,
        content_text: str,
        chosen_lang: str,
        req_id: int,
        correlation_id: str | None,
        *,
        summary: dict[str, Any] | None = None,
        silent: bool = False,
    ) -> None:
        """Generate and persist additional insights using the LLM."""
        logger.info(
            "insights_flow_started",
            extra={"cid": correlation_id, "content_len": len(content_text), "lang": chosen_lang},
        )

        try:
            insights = await self.llm_summarizer.generate_additional_insights(
                message,
                content_text=content_text,
                chosen_lang=chosen_lang,
                req_id=req_id,
                correlation_id=correlation_id,
                summary=summary,
            )

            if insights:
                logger.info(
                    "insights_generated_successfully",
                    extra={
                        "cid": correlation_id,
                        "facts_count": len(insights.get("new_facts", [])),
                        "has_overview": bool(insights.get("topic_overview")),
                    },
                )

                # Only send insights message if not in silent mode
                if not silent:
                    await self.response_formatter.send_additional_insights_message(
                        message, insights, correlation_id
                    )
                    logger.info("insights_message_sent", extra={"cid": correlation_id})
                else:
                    logger.info("insights_generated_silently", extra={"cid": correlation_id})

                try:
                    self.db.update_summary_insights(req_id, insights)
                    logger.debug(
                        "insights_persisted", extra={"cid": correlation_id, "request_id": req_id}
                    )
                except Exception as exc:  # noqa: BLE001
                    raise_if_cancelled(exc)
                    logger.error(
                        "persist_insights_error",
                        extra={"cid": correlation_id, "error": str(exc)},
                    )
            else:
                logger.warning(
                    "insights_generation_returned_empty",
                    extra={"cid": correlation_id, "reason": "LLM returned None or empty insights"},
                )

        except Exception as exc:  # noqa: BLE001
            raise_if_cancelled(exc)
            logger.exception(
                "insights_flow_error",
                extra={"cid": correlation_id, "error": str(exc)},
            )

    async def _load_system_prompt(self, lang: str) -> str:
        """Load system prompt file based on language."""
        return _get_system_prompt(lang)

    def _is_summary_complete(self, summary: dict[str, Any]) -> bool:
        """Check if a summary has the essential fields populated."""
        if not isinstance(summary, dict):
            return False

        # Essential fields that must be present and non-empty
        essential_fields = [
            ("summary_250", "summary_250"),
            ("summary_1000", "summary_1000"),
            ("tldr", "tldr"),
        ]

        # Check essential fields
        for field, lookup in essential_fields:
            value = summary.get(lookup)
            if lookup == "summary_1000" and not value:
                value = summary.get("tldr")
            if lookup == "tldr" and not value:
                value = summary.get("summary_1000")
            if not value or not str(value).strip():
                return False

        # At least one of these should have content
        content_fields = [
            "key_ideas",
            "topic_tags",
            "entities",
        ]

        has_content = False
        for field in content_fields:
            value = summary.get(field)
            if field == "entities":
                if isinstance(value, dict) and any(
                    isinstance(v, list) and len(v) > 0 for v in value.values()
                ):
                    has_content = True
                    break
            elif isinstance(value, list) and len(value) > 0:
                has_content = True
                break

        if not has_content:
            logger.debug(
                "cached_summary_missing_optional_content",
                extra={"missing_fields": content_fields},
            )

        return True

    def _get_missing_summary_fields(self, summary: dict[str, Any]) -> list[str]:
        """Get list of missing or empty essential fields."""
        if not isinstance(summary, dict):
            return ["invalid_summary_format"]

        missing = []
        essential_fields = [
            ("summary_250", "summary_250"),
            ("summary_1000", "summary_1000"),
            ("tldr", "tldr"),
        ]

        for field, lookup in essential_fields:
            value = summary.get(lookup)
            if lookup == "summary_1000" and not value:
                value = summary.get("tldr")
            if lookup == "tldr" and not value:
                value = summary.get("summary_1000")
            if not value or not str(value).strip():
                missing.append(field)

        return missing

    async def _maybe_reply_with_cached_summary(
        self,
        message: Any,
        url_text: str,
        *,
        correlation_id: str | None,
        interaction_id: int | None,
        silent: bool = False,
    ) -> bool:
        """Return True if an existing summary was reused."""
        try:
            norm = normalize_url(url_text)
        except Exception:
            return False

        dedupe = url_hash_sha256(norm)
        existing_req = await self.db.async_get_request_by_dedupe_hash(dedupe)
        if not isinstance(existing_req, Mapping):
            getter = getattr(self.db, "get_request_by_dedupe_hash", None)
            existing_req = getter(dedupe) if callable(getter) else None

        if isinstance(existing_req, Mapping):
            existing_req = dict(existing_req)

        if not existing_req:
            return False

        req_id = int(existing_req["id"])
        summary_row = await self.db.async_get_summary_by_request(req_id)
        if not isinstance(summary_row, Mapping):
            getter = getattr(self.db, "get_summary_by_request", None)
            summary_row = getter(req_id) if callable(getter) else None

        if isinstance(summary_row, Mapping):
            summary_row = dict(summary_row)

        if not summary_row:
            return False

        payload = summary_row.get("json_payload")
        if payload is None:
            logger.debug(
                "cached_summary_empty_payload",
                extra={"request_id": req_id, "cid": correlation_id},
            )
            return False

        if isinstance(payload, Mapping):
            shaped = dict(payload)
        elif isinstance(payload, str):
            try:
                shaped = json.loads(payload)
            except json.JSONDecodeError:
                logger.warning(
                    "cached_summary_decode_failed",
                    extra={"request_id": req_id, "cid": correlation_id},
                )
                return False
        else:
            logger.warning(
                "cached_summary_unsupported_payload",
                extra={"request_id": req_id, "cid": correlation_id, "type": type(payload).__name__},
            )
            return False

        # Validate that the summary is complete and has essential fields
        if not self._is_summary_complete(shaped):
            logger.debug(
                "cached_summary_incomplete",
                extra={
                    "request_id": req_id,
                    "cid": correlation_id,
                    "missing_fields": self._get_missing_summary_fields(shaped),
                },
            )
            return False

        if correlation_id:
            try:
                self.db.update_request_correlation_id(req_id, correlation_id)
            except Exception as exc:  # noqa: BLE001
                raise_if_cancelled(exc)
                logger.error("persist_cid_error", extra={"error": str(exc), "cid": correlation_id})

        # Skip Telegram responses if silent
        if not silent:
            await self.response_formatter.send_url_accepted_notification(
                message, norm, correlation_id or "", silent=silent
            )
            await self.response_formatter.send_cached_summary_notification(message, silent=silent)
            # Resolve model used previously for this request and pass a stub to avoid 'unknown'
            try:
                model_name = self.db.get_latest_llm_model_by_request_id(req_id)
            except Exception:
                model_name = None
            llm_stub = type("LLMStub", (), {"model": model_name})()
            await self.response_formatter.send_structured_summary_response(
                message, shaped, llm_stub
            )

            insights_raw = summary_row.get("insights_json")
            insights_payload: dict[str, Any] | None
            if isinstance(insights_raw, Mapping):
                insights_payload = dict(cast(Mapping[str, Any], insights_raw))
            elif isinstance(insights_raw, str) and insights_raw.strip():
                try:
                    decoded = json.loads(insights_raw)
                except json.JSONDecodeError:
                    logger.warning(
                        "cached_insights_decode_failed",
                        extra={"request_id": req_id, "cid": correlation_id},
                    )
                    decoded = None
                if isinstance(decoded, Mapping):
                    insights_payload = dict(cast(Mapping[str, Any], decoded))
                else:
                    insights_payload = None
            else:
                insights_payload = None
            if insights_payload:
                await self.response_formatter.send_additional_insights_message(
                    message, dict(insights_payload), correlation_id
                )

        await self.db.async_update_request_status(req_id, "ok")

        self._audit(
            "INFO",
            "summary_cache_hit",
            {
                "request_id": req_id,
                "url": norm,
                "cid": correlation_id,
            },
        )

        if interaction_id:
            await async_safe_update_user_interaction(
                self.db,
                interaction_id=interaction_id,
                response_sent=True,
                response_type="summary",
                request_id=req_id,
                logger_=logger,
            )

        logger.info(
            "summary_cache_reused",
            extra={"request_id": req_id, "cid": correlation_id, "normalized_url": norm},
        )
        return True
