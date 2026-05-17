"""Tests for the optional LLM-backed content tier classifier.

The classifier is consulted only when the keyword/domain heuristics in
``classify_content`` produce a tie (``tech_weight == socio_weight >= 1``).
It must (1) be a no-op when disabled, (2) return a parsed ContentTier on
a clean label, (3) fail-soft to None on LLM error / timeout / malformed
label, and (4) avoid duplicating calls for the same content via a short
in-process cache.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from app.adapter_models.llm.llm_models import LLMCallResult
from app.core.call_status import CallStatus
from app.core.content_classifier import ContentTier, LLMTierClassifier


@dataclass
class FakeLLMClient:
    """Minimal fake honouring the slice of LLMClientProtocol we touch."""

    reply_text: str = "technical"
    status: CallStatus = CallStatus.OK
    calls: list[dict[str, Any]] = field(default_factory=list)
    raise_on_call: Exception | None = None

    @property
    def provider_name(self) -> str:
        return "fake"

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        top_p: float | None = None,
        request_id: int | None = None,
        response_format: dict[str, Any] | None = None,
        model_override: str | None = None,
        fallback_models_override: Any = None,
        on_stream_delta: Any = None,
    ) -> LLMCallResult:
        if self.raise_on_call is not None:
            raise self.raise_on_call
        self.calls.append(
            {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "model_override": model_override,
            }
        )
        return LLMCallResult(
            status=self.status,
            model=model_override or "fake-model",
            response_text=self.reply_text,
            error_text=None if self.status is CallStatus.OK else "boom",
        )

    async def chat_structured(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    async def aclose(self) -> None:
        return None


@pytest.fixture
def client() -> FakeLLMClient:
    return FakeLLMClient()


class TestDisabledByDefault:
    async def test_returns_none_when_disabled(self, client: FakeLLMClient) -> None:
        classifier = LLMTierClassifier(client=client, model="fake-model", enabled=False)
        result = await classifier.resolve_tie("some interdisciplinary text", url=None)
        assert result is None
        assert client.calls == []


class TestLabelParsing:
    @pytest.mark.parametrize(
        ("reply", "expected"),
        [
            ("technical", ContentTier.TECHNICAL),
            ("Technical", ContentTier.TECHNICAL),
            ("  TECHNICAL\n", ContentTier.TECHNICAL),
            ("sociopolitical", ContentTier.SOCIOPOLITICAL),
            ("Sociopolitical.", ContentTier.SOCIOPOLITICAL),
            ("default", ContentTier.DEFAULT),
            ("Tier: technical", ContentTier.TECHNICAL),
        ],
    )
    async def test_parses_label(
        self, client: FakeLLMClient, reply: str, expected: ContentTier
    ) -> None:
        client.reply_text = reply
        classifier = LLMTierClassifier(client=client, model="m", enabled=True)
        result = await classifier.resolve_tie("text", url=None)
        assert result is expected

    async def test_unknown_label_returns_none(self, client: FakeLLMClient) -> None:
        client.reply_text = "🤷 not a label"
        classifier = LLMTierClassifier(client=client, model="m", enabled=True)
        assert await classifier.resolve_tie("text", url=None) is None


class TestFailureSoftFallthrough:
    async def test_call_status_error_returns_none(self, client: FakeLLMClient) -> None:
        client.status = CallStatus.ERROR
        client.reply_text = ""
        classifier = LLMTierClassifier(client=client, model="m", enabled=True)
        assert await classifier.resolve_tie("text", url=None) is None

    async def test_exception_returns_none(self, client: FakeLLMClient) -> None:
        client.raise_on_call = TimeoutError("timeout")
        classifier = LLMTierClassifier(client=client, model="m", enabled=True)
        assert await classifier.resolve_tie("text", url=None) is None

    async def test_empty_text_returns_none_without_calling(self, client: FakeLLMClient) -> None:
        classifier = LLMTierClassifier(client=client, model="m", enabled=True)
        assert await classifier.resolve_tie("", url=None) is None
        assert client.calls == []


class TestCaching:
    async def test_repeated_call_uses_cache(self, client: FakeLLMClient) -> None:
        client.reply_text = "technical"
        classifier = LLMTierClassifier(client=client, model="m", enabled=True)
        first = await classifier.resolve_tie("Same content body", url="https://x.test/a")
        second = await classifier.resolve_tie("Same content body", url="https://x.test/a")
        assert first is ContentTier.TECHNICAL
        assert second is ContentTier.TECHNICAL
        assert len(client.calls) == 1

    async def test_cache_keyed_by_url_when_present(self, client: FakeLLMClient) -> None:
        client.reply_text = "technical"
        classifier = LLMTierClassifier(client=client, model="m", enabled=True)
        await classifier.resolve_tie("body", url="https://x.test/a")
        await classifier.resolve_tie("body", url="https://x.test/b")
        # Different URLs => two distinct cache keys.
        assert len(client.calls) == 2


class TestTieBreakIntegration:
    """`classify_content_async` is the tie-aware variant that consults
    the LLM classifier only when the heuristic returns DEFAULT due to a
    tie (``tech_weight == socio_weight >= 1``). For unambiguous inputs
    the LLM must never be called."""

    async def test_unambiguous_input_does_not_call_llm(self, client: FakeLLMClient) -> None:
        from app.core.content_classifier import classify_content_async

        classifier = LLMTierClassifier(client=client, model="m", enabled=True)
        # Strong technical signal: github.com URL → +2 domain weight.
        tier = await classify_content_async(
            "boring text",
            url="https://github.com/foo/bar",
            llm_classifier=classifier,
        )
        assert tier is ContentTier.TECHNICAL
        assert client.calls == []

    async def test_tie_triggers_llm_classifier(self, client: FakeLLMClient) -> None:
        from app.core.content_classifier import classify_content_async

        client.reply_text = "technical"
        classifier = LLMTierClassifier(client=client, model="m", enabled=True)
        # Pure keyword tie: text balanced between technical and sociopolitical
        # produces tech_weight == socio_weight == 1.
        text = (
            "algorithm runtime compiler kernel database performance optimisation "
            "election democracy policy government legislature regulation citizens"
        )
        tier = await classify_content_async(text, url=None, llm_classifier=classifier)
        assert tier is ContentTier.TECHNICAL
        assert len(client.calls) == 1

    async def test_disabled_classifier_falls_through_to_default(
        self, client: FakeLLMClient
    ) -> None:
        from app.core.content_classifier import classify_content_async

        classifier = LLMTierClassifier(client=client, model="m", enabled=False)
        text = (
            "algorithm runtime compiler kernel database performance optimisation "
            "election democracy policy government legislature regulation citizens"
        )
        tier = await classify_content_async(text, url=None, llm_classifier=classifier)
        assert tier is ContentTier.DEFAULT
        assert client.calls == []

    async def test_no_classifier_falls_through_to_default(self) -> None:
        from app.core.content_classifier import classify_content_async

        text = (
            "algorithm runtime compiler kernel database performance optimisation "
            "election democracy policy government legislature regulation citizens"
        )
        tier = await classify_content_async(text, url=None, llm_classifier=None)
        assert tier is ContentTier.DEFAULT


class TestConfigDefaults:
    def test_classifier_disabled_by_default(self) -> None:
        from app.config.llm import ModelRoutingConfig

        cfg = ModelRoutingConfig()
        assert cfg.llm_classifier_enabled is False

    def test_classifier_default_model_is_a_flash_tier(self) -> None:
        from app.config.llm import ModelRoutingConfig

        cfg = ModelRoutingConfig()
        # Must be one of the cheap models — default chosen by task spec.
        assert cfg.llm_classifier_model
        assert "flash" in cfg.llm_classifier_model or "mini" in cfg.llm_classifier_model


class TestPromptShape:
    async def test_prompt_is_short_and_asks_for_label(self, client: FakeLLMClient) -> None:
        client.reply_text = "default"
        classifier = LLMTierClassifier(client=client, model="m", enabled=True)
        await classifier.resolve_tie(
            "A piece of interdisciplinary policy commentary about AI",
            url="https://example.test/article",
        )
        assert len(client.calls) == 1
        call = client.calls[0]
        joined = " ".join(m["content"] for m in call["messages"])
        # Must mention the three allowed tiers verbatim.
        assert "technical" in joined.lower()
        assert "sociopolitical" in joined.lower()
        assert "default" in joined.lower()
        # max_tokens is bounded — single label, not an essay.
        assert call["max_tokens"] is not None and call["max_tokens"] <= 16
