"""Request assembly for interactive summarization."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.adapters.content.llm_response_workflow import (
    LLMInteractionConfig,
    LLMRepairContext,
    LLMRequestConfig,
    LLMSummaryPersistenceSettings,
    LLMWorkflowNotifications,
)
from app.adapters.content.llm_summarizer_text import truncate_content_text
from app.core.content_cleaner import clean_content_for_llm
from app.core.lang import LANG_RU

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.adapters.content.summarization_models import InteractiveSummaryRequest
    from app.adapters.content.summarization_runtime import SummarizationRuntime

logger = logging.getLogger(__name__)


def detect_content_type_hint(content: str) -> str:
    """Return a lightweight prompt hint inferred from content heuristics."""
    lower = content[:2000].lower()
    if any(kw in lower for kw in ("abstract", "methodology", "doi:", "et al.", "arxiv")):
        return "CONTENT HINT: Research paper. Focus on methodology, findings, and limitations.\n"
    if any(
        kw in lower for kw in ("step 1", "how to", "tutorial", "prerequisites", "getting started")
    ):
        return "CONTENT HINT: Tutorial. Focus on steps, prerequisites, and outcomes.\n"
    if any(
        kw in lower
        for kw in ("breaking:", "reuters", "reported today", "press release", "associated press")
    ):
        return "CONTENT HINT: News article. Focus on who, what, when, where, why.\n"
    if any(
        kw in lower for kw in ("in my opinion", "i think", "i believe", "editorial", "commentary")
    ):
        return (
            "CONTENT HINT: Opinion piece. Focus on the author's thesis and supporting arguments.\n"
        )
    return ""


def log_llm_content_validation(
    *,
    cfg: Any,
    content_text: str,
    system_prompt: str,
    user_content: str,
    correlation_id: str | None,
) -> None:
    """Emit a uniform validation log before sending prompt content to the LLM."""
    logger.info(
        "llm_content_validation",
        extra={
            "cid": correlation_id,
            "system_prompt_len": len(system_prompt),
            "user_content_len": len(user_content),
            "text_for_summary_len": len(content_text),
            "text_preview": (
                content_text[:200] + "..." if len(content_text) > 200 else content_text
            ),
            "has_content": bool(content_text.strip()),
            "structured_output_config": {
                "enabled": cfg.openrouter.enable_structured_outputs,
                "mode": cfg.openrouter.structured_output_mode,
                "require_parameters": cfg.openrouter.require_parameters,
                "auto_fallback": cfg.openrouter.auto_fallback_structured,
            },
        },
    )


def _clamp_float(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


@dataclass(slots=True)
class SummaryExecutionPlan:
    """Prepared request data for interactive summary execution."""

    content_for_summary: str
    user_content: str
    base_model: str
    requests: list[LLMRequestConfig]
    repair_context: LLMRepairContext
    notifications: LLMWorkflowNotifications
    interaction_config: LLMInteractionConfig
    persistence: LLMSummaryPersistenceSettings
    stream_coordinator: Any | None


class SummaryRequestFactory:
    """Prepare interactive summary workflow inputs."""

    def __init__(
        self,
        *,
        runtime: SummarizationRuntime,
        select_max_tokens: Callable[[str], int | None],
        stream_coordinator_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._runtime = runtime
        self._select_max_tokens = select_max_tokens
        self._stream_coordinator_factory = stream_coordinator_factory

    async def prepare_interactive_request(
        self,
        request: InteractiveSummaryRequest,
        *,
        callbacks: Any,
    ) -> SummaryExecutionPlan:
        """Build the full workflow input bundle for an interactive summary."""
        content_for_summary, model_override = self._prepare_summary_content(
            content_text=request.content_text,
            max_chars=request.max_chars,
            correlation_id=request.correlation_id,
            images=request.images,
        )
        search_context = await self._runtime.search_enricher.enrich(
            content_text=content_for_summary,
            chosen_lang=request.chosen_lang,
            correlation_id=request.correlation_id,
        )
        user_content = self.build_summary_user_content(
            content_for_summary=content_for_summary,
            chosen_lang=request.chosen_lang,
            search_context=search_context,
        )
        log_llm_content_validation(
            cfg=self._runtime.cfg,
            content_text=content_for_summary,
            system_prompt=request.system_prompt,
            user_content=user_content,
            correlation_id=request.correlation_id,
        )
        messages = self.build_summary_messages(
            request.system_prompt,
            user_content,
            images=request.images,
        )

        base_model = model_override or self._runtime.cfg.openrouter.model
        requests = self._build_summary_requests(
            messages=messages,
            base_model=base_model,
            content_for_summary=content_for_summary,
            user_content=user_content,
            silent=request.silent,
        )
        stream_coordinator = self._configure_streaming(
            requests=requests,
            message=request.message,
            correlation_id=request.correlation_id,
            silent=request.silent,
        )

        return SummaryExecutionPlan(
            content_for_summary=content_for_summary,
            user_content=user_content,
            base_model=base_model,
            requests=requests,
            repair_context=self.build_summary_repair_context(
                request.system_prompt,
                user_content,
            ),
            notifications=callbacks.build_notifications(),
            interaction_config=callbacks.build_interaction_config(),
            persistence=callbacks.build_persistence_settings(),
            stream_coordinator=stream_coordinator,
        )

    def build_summary_user_content(
        self,
        *,
        content_for_summary: str,
        chosen_lang: str,
        search_context: str,
    ) -> str:
        """Build user prompt content for the summary request."""
        content_hint = detect_content_type_hint(content_for_summary)
        user_content = (
            "Analyze the following content and output ONLY a valid JSON object that matches "
            "the system contract exactly. "
            f"Respond in {'Russian' if chosen_lang == LANG_RU else 'English'}. "
            "Do NOT include any text outside the JSON.\n\n"
            f"{content_hint}"
            f"CONTENT START\n{content_for_summary}\nCONTENT END"
        )
        if search_context:
            return f"{user_content}\n\n{search_context}"
        return user_content

    def build_summary_messages(
        self,
        system_prompt: str,
        user_content: str,
        *,
        images: list[str] | None,
    ) -> list[dict[str, Any]]:
        """Build multimodal chat messages for the summary request."""
        if not images:
            return [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]

        content_parts: list[dict[str, Any]] = [{"type": "text", "text": user_content}]
        for uri in images:
            content_parts.append({"type": "image_url", "image_url": {"url": uri}})

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content_parts},
        ]

    def build_summary_repair_context(
        self, system_prompt: str, user_content: str
    ) -> LLMRepairContext:
        """Build JSON-repair fallback configuration."""
        return LLMRepairContext(
            base_messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            repair_response_format=self._runtime.workflow.build_structured_response_format(
                mode="json_object"
            ),
            repair_max_tokens=self._select_max_tokens(user_content),
            default_prompt=(
                "Your previous message was not a valid JSON object. Respond with ONLY a corrected JSON "
                "that matches the schema exactly."
            ),
            missing_fields_prompt=(
                "Your previous message was not a valid JSON object. Respond with ONLY a corrected JSON that "
                "matches the schema exactly. Ensure `summary_250` and `tldr` contain non-empty informative text."
            ),
        )

    def _prepare_summary_content(
        self,
        *,
        content_text: str,
        max_chars: int,
        correlation_id: str | None,
        images: list[str] | None,
    ) -> tuple[str, str | None]:
        """Choose truncation/model strategy and return cleaned content."""
        content_for_summary = content_text
        model_override = self._runtime.cfg.attachment.vision_model if images else None

        if len(content_text) > max_chars:
            if self._runtime.cfg.openrouter.long_context_model:
                model_override = self._runtime.cfg.openrouter.long_context_model
            else:
                content_for_summary = truncate_content_text(content_text, max_chars)
                logger.info(
                    "summary_content_truncated",
                    extra={
                        "cid": correlation_id,
                        "original_len": len(content_text),
                        "truncated_len": len(content_for_summary),
                        "max_chars": max_chars,
                    },
                )

        return clean_content_for_llm(content_for_summary), model_override

    def _build_summary_requests(
        self,
        *,
        messages: list[dict[str, Any]],
        base_model: str,
        content_for_summary: str,
        user_content: str,
        silent: bool,
    ) -> list[LLMRequestConfig]:
        """Construct ordered LLM attempts for summary generation."""
        response_format_schema = self._runtime.workflow.build_structured_response_format()
        response_format_json = self._runtime.workflow.build_structured_response_format(
            mode="json_object"
        )
        max_tokens_schema = self._select_max_tokens(content_for_summary)
        max_tokens_json = self._select_max_tokens(user_content)

        base_temperature = self._runtime.cfg.openrouter.temperature
        base_top_p = (
            self._runtime.cfg.openrouter.top_p
            if self._runtime.cfg.openrouter.top_p is not None
            else 0.9
        )
        json_temperature = self._runtime.cfg.openrouter.summary_temperature_json_fallback or (
            _clamp_float(base_temperature - 0.05, 0.0, 0.5)
        )
        json_top_p = self._runtime.cfg.openrouter.summary_top_p_json_fallback or _clamp_float(
            base_top_p,
            0.0,
            0.95,
        )

        requests = [
            self._make_request(
                preset="schema_strict",
                model_name=base_model,
                messages=messages,
                response_format=response_format_schema,
                max_tokens=max_tokens_schema,
                temperature=base_temperature,
                top_p=base_top_p,
                silent=silent,
            ),
            self._make_request(
                preset="json_object_guardrail",
                model_name=base_model,
                messages=messages,
                response_format=response_format_json,
                max_tokens=max_tokens_json,
                temperature=json_temperature,
                top_p=json_top_p,
                silent=silent,
            ),
        ]

        added_flash_models: set[str] = set()
        flash_models: list[str] = []
        flash_model = getattr(self._runtime.cfg.openrouter, "flash_model", None)
        if flash_model:
            flash_models.append(flash_model)
        flash_fallback_models = getattr(self._runtime.cfg.openrouter, "flash_fallback_models", [])
        if flash_fallback_models:
            flash_models.extend(flash_fallback_models)

        for model_name in flash_models:
            if not model_name or model_name == base_model or model_name in added_flash_models:
                continue
            requests.append(
                self._make_request(
                    preset="json_object_flash",
                    model_name=model_name,
                    messages=messages,
                    response_format=response_format_json,
                    max_tokens=max_tokens_json,
                    temperature=json_temperature,
                    top_p=json_top_p,
                    silent=silent,
                )
            )
            added_flash_models.add(model_name)

        fallback_models = [
            model
            for model in self._runtime.cfg.openrouter.fallback_models
            if model and model != base_model
        ]
        if fallback_models:
            fallback_model = fallback_models[0]
            if fallback_model not in added_flash_models:
                requests.append(
                    self._make_request(
                        preset="json_object_fallback",
                        model_name=fallback_model,
                        messages=messages,
                        response_format=response_format_json,
                        max_tokens=max_tokens_json,
                        temperature=json_temperature,
                        top_p=json_top_p,
                        silent=silent,
                    )
                )
        return requests

    def _make_request(
        self,
        *,
        preset: str,
        model_name: str,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any],
        max_tokens: int | None,
        temperature: float,
        top_p: float | None,
        silent: bool,
    ) -> LLMRequestConfig:
        return LLMRequestConfig(
            preset_name=preset,
            messages=messages,
            response_format=response_format,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            model_override=model_name,
            silent=silent,
        )

    def _summary_streaming_enabled(self, *, silent: bool) -> bool:
        if silent:
            return False
        if not getattr(self._runtime.cfg.runtime, "summary_streaming_enabled", True):
            return False
        if getattr(self._runtime.cfg.runtime, "summary_streaming_mode", "section") != "section":
            return False
        telegram_cfg = getattr(self._runtime.cfg, "telegram", None)
        if telegram_cfg is None:
            return False
        if not getattr(telegram_cfg, "draft_streaming_enabled", True):
            return False

        scope = getattr(
            self._runtime.cfg.runtime,
            "summary_streaming_provider_scope",
            "openrouter",
        )
        provider_name = str(
            getattr(self._runtime.openrouter, "provider_name", "openrouter")
        ).lower()
        scope = str(scope).strip().lower()
        if scope == "disabled":
            return False
        if scope == "all":
            return True
        return provider_name == scope

    def _configure_streaming(
        self,
        *,
        requests: list[LLMRequestConfig],
        message: Any,
        correlation_id: str | None,
        silent: bool,
    ) -> Any | None:
        if not self._summary_streaming_enabled(silent=silent):
            return None
        if self._stream_coordinator_factory is None:
            return None

        stream_coordinator = self._stream_coordinator_factory(
            response_formatter=self._runtime.response_formatter,
            message=message,
            correlation_id=correlation_id,
        )
        for request in requests:
            request.stream = True
            request.on_stream_delta = stream_coordinator.on_delta
        return stream_coordinator
