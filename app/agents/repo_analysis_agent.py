"""Repo analysis agent with self-correction feedback loop."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from pydantic import ValidationError

from app.core.logging_utils import get_logger
from app.core.repo_analysis_contract import parse_and_validate_repo_analysis

if TYPE_CHECKING:
    from app.core.repo_analysis_schema import RepoAnalysis, RepoAnalysisInput

logger = get_logger(__name__)

_PROMPT_DIR = Path(__file__).parent.parent / "prompts"


def _provider_from_model(model_name: str | None) -> str:
    """Derive a provider label from an OpenRouter-style model name.

    Handles ``vendor/model-name`` patterns (e.g. ``openai/gpt-4o``,
    ``anthropic/claude-3-5-sonnet``) and bare names.  Returns ``"unknown"``
    when the name is empty or has no slash.
    """
    if not model_name:
        return "unknown"
    if "/" in model_name:
        return model_name.split("/", 1)[0]
    return "unknown"


@runtime_checkable
class LLMServiceProtocol(Protocol):
    """Minimal LLM interface required by RepoAnalysisAgent."""

    async def call(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        correlation_id: str,
    ) -> str:
        """Return the raw text response from the LLM."""
        ...


@runtime_checkable
class LLMRepoProtocol(Protocol):
    """Minimal persistence interface for LLMCall rows."""

    async def async_insert_llm_call(self, payload: dict[str, Any]) -> int | None:
        """Persist a single LLM call record and return its id (optional)."""
        ...


class RepoAnalysisAgent:
    """Analyse a GitHub repository via LLM with a validation retry loop.

    The agent:
    - Loads the correct system prompt for the chosen language.
    - Serialises ``RepoAnalysisInput`` as JSON and sends it to the LLM.
    - Validates the response with ``parse_and_validate_repo_analysis``.
    - On failure, prepends the error as a correction preamble and retries.
    - Persists one ``LLMCall``-shaped record per attempt via ``llm_repo``
      (optional; skipped when not provided).
    """

    def __init__(
        self,
        llm_service: LLMServiceProtocol,
        llm_repo: LLMRepoProtocol | None = None,
        request_id: int | None = None,
        model_name: str | None = None,
    ) -> None:
        self._llm = llm_service
        self._llm_repo = llm_repo
        self._request_id = request_id
        self._model_name = model_name

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze(
        self,
        input: RepoAnalysisInput,
        *,
        chosen_lang: Literal["en", "ru"] = "en",
        correlation_id: str,
        max_attempts: int = 3,
    ) -> RepoAnalysis | None:
        """Run LLM analysis with a retry-on-validation-error loop.

        Returns a ``RepoAnalysis`` on success, or ``None`` after
        ``max_attempts`` consecutive failures.
        """
        system_prompt = self._load_system_prompt(chosen_lang)
        user_prompt = self._build_user_prompt(input)
        previous_error: str | None = None

        for attempt_index in range(1, max_attempts + 1):
            attempt_trigger = "initial" if attempt_index == 1 else "repair_loop"
            effective_prompt = (
                self._prepend_correction(user_prompt, previous_error)
                if previous_error
                else user_prompt
            )

            logger.info(
                "repo_analysis_attempt",
                extra={
                    "event": "repo_analysis_attempt",
                    "correlation_id": correlation_id,
                    "full_name": input.full_name,
                    "attempt_index": attempt_index,
                    "attempt_trigger": attempt_trigger,
                },
            )

            raw_response: str = ""
            try:
                raw_response = await self._llm.call(
                    system_prompt=system_prompt,
                    user_prompt=effective_prompt,
                    correlation_id=correlation_id,
                )
            except Exception as exc:
                logger.error(
                    "repo_analysis_llm_error",
                    extra={
                        "event": "repo_analysis_llm_error",
                        "correlation_id": correlation_id,
                        "full_name": input.full_name,
                        "attempt_index": attempt_index,
                        "error": str(exc),
                    },
                )
                previous_error = f"LLM call failed: {exc}"
                await self._persist(
                    correlation_id=correlation_id,
                    attempt_index=attempt_index,
                    attempt_trigger=attempt_trigger,
                    response_text=raw_response,
                    status="error",
                    error_text=str(exc),
                )
                continue

            await self._persist(
                correlation_id=correlation_id,
                attempt_index=attempt_index,
                attempt_trigger=attempt_trigger,
                response_text=raw_response,
                status="ok",
                error_text=None,
            )

            try:
                result = parse_and_validate_repo_analysis(raw_response)
            except (ValidationError, Exception) as exc:
                error_msg = str(exc)
                logger.warning(
                    "repo_analysis_validation_failed",
                    extra={
                        "event": "repo_analysis_validation_failed",
                        "correlation_id": correlation_id,
                        "full_name": input.full_name,
                        "attempt_index": attempt_index,
                        "error": error_msg,
                    },
                )
                previous_error = error_msg
                continue

            logger.info(
                "repo_analysis_success",
                extra={
                    "event": "repo_analysis_success",
                    "correlation_id": correlation_id,
                    "full_name": input.full_name,
                    "attempt_index": attempt_index,
                    "confidence": result.confidence,
                },
            )
            return result

        logger.error(
            "repo_analysis_failed",
            extra={
                "event": "repo_analysis_failed",
                "correlation_id": correlation_id,
                "full_name": input.full_name,
                "max_attempts": max_attempts,
            },
        )
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_system_prompt(self, lang: Literal["en", "ru"]) -> str:
        prompt_file = _PROMPT_DIR / f"repo_analysis_system_{lang}.txt"
        try:
            return prompt_file.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning(
                "repo_analysis_prompt_load_failed",
                extra={"lang": lang, "path": str(prompt_file), "error": str(exc)},
            )
            return (
                "You are a software repository analyst. "
                "Return ONLY a valid JSON object matching the RepoAnalysis schema."
            )

    @staticmethod
    def _build_user_prompt(input: RepoAnalysisInput) -> str:
        return (
            "Analyse the following repository metadata and return a JSON object "
            "that strictly matches the RepoAnalysis schema.\n\n"
            + json.dumps(input.model_dump(), ensure_ascii=False, indent=2)
        )

    @staticmethod
    def _prepend_correction(base_prompt: str, error: str) -> str:
        preamble = (
            "Your previous output failed validation:\n"
            f"{error}\n\n"
            "Fix the issues above and re-emit valid JSON that matches the schema.\n\n"
        )
        return preamble + base_prompt

    async def _persist(
        self,
        *,
        correlation_id: str,
        attempt_index: int,
        attempt_trigger: str,
        response_text: str,
        status: str,
        error_text: str | None,
    ) -> None:
        if self._llm_repo is None:
            return
        payload: dict[str, Any] = {
            "request_id": self._request_id,
            "provider": _provider_from_model(self._model_name),
            "model": self._model_name,
            "response_text": response_text,
            "status": status,
            "error_text": error_text,
            "attempt_index": attempt_index,
            "attempt_trigger": attempt_trigger,
            "correlation_id": correlation_id,
        }
        try:
            await self._llm_repo.async_insert_llm_call(payload)
        except Exception as exc:
            logger.warning(
                "repo_analysis_persist_failed",
                extra={
                    "event": "repo_analysis_persist_failed",
                    "correlation_id": correlation_id,
                    "attempt_index": attempt_index,
                    "error": str(exc),
                },
            )
