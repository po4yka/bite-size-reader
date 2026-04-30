"""Bounded LLM-as-judge stage for signal scoring."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, ValidationError

from app.core.call_status import CallStatus
from app.core.json_utils import extract_json
from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from app.adapters.llm.protocol import LLMClientProtocol

logger = get_logger(__name__)
PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"


class SignalJudgeOutput(BaseModel):
    relevance_score: float = Field(ge=0.0, le=1.0)
    decision: str = Field(pattern="^(queue|skip|hide_source)$")
    reason: str = Field(min_length=1, max_length=500)


@dataclass(slots=True, frozen=True)
class SignalJudgeDecision:
    llm_score: float
    decision: str
    reason: str
    cost_usd: float | None
    latency_ms: int | None
    model: str | None

    def evidence(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "model": self.model,
            "latency_ms": self.latency_ms,
        }


class SignalJudgeService:
    """Judge only the capped top slice of scored candidates."""

    def __init__(
        self,
        *,
        llm_client: LLMClientProtocol,
        daily_budget_usd: float = 0.25,
        lang: str = "en",
    ) -> None:
        self._llm = llm_client
        self._daily_budget_usd = max(0.0, daily_budget_usd)
        self._lang = lang
        self._spent_usd = 0.0

    async def judge(
        self,
        scored_candidates: list[Any],
        *,
        rows_by_item_id: dict[int, dict[str, Any]],
    ) -> dict[int, SignalJudgeDecision]:
        decisions: dict[int, SignalJudgeDecision] = {}
        for candidate in scored_candidates:
            if not getattr(candidate, "should_reach_llm_judge", False):
                continue
            if self._spent_usd >= self._daily_budget_usd:
                logger.warning("signal_judge_budget_exhausted")
                break
            row = rows_by_item_id.get(int(candidate.feed_item_id), {})
            decision = await self._judge_one(row)
            if decision is None:
                continue
            if decision.cost_usd:
                self._spent_usd += decision.cost_usd
            decisions[int(candidate.feed_item_id)] = decision
        return decisions

    async def _judge_one(self, row: dict[str, Any]) -> SignalJudgeDecision | None:
        prompt = self._build_prompt(row)
        for attempt in range(2):
            result = await self._llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=350,
                response_format=_response_format(),
            )
            if result.status != CallStatus.OK or result.error_text:
                logger.warning("signal_judge_llm_error", extra={"error": result.error_text})
                return None
            parsed = self._parse_output(result.response_text or "")
            if parsed is None:
                if attempt == 0:
                    prompt += "\n\nReturn only valid JSON matching the requested schema."
                    continue
                return None
            return SignalJudgeDecision(
                llm_score=parsed.relevance_score,
                decision=parsed.decision,
                reason=parsed.reason,
                cost_usd=result.cost_usd,
                latency_ms=result.latency_ms,
                model=result.model,
            )
        return None

    def _build_prompt(self, row: dict[str, Any]) -> str:
        template = _load_prompt(self._lang)
        return template.format(
            title=str(row.get("title") or "")[:300],
            url=str(row.get("canonical_url") or "")[:500],
            content=str(row.get("content_text") or "")[:4000],
        )

    @staticmethod
    def _parse_output(raw_text: str) -> SignalJudgeOutput | None:
        parsed = extract_json(raw_text)
        if not isinstance(parsed, dict):
            return None
        try:
            return SignalJudgeOutput.model_validate(parsed)
        except ValidationError:
            logger.warning("signal_judge_schema_invalid", extra={"raw": raw_text[:200]})
            return None


def _load_prompt(lang: str) -> str:
    safe_lang = "ru" if lang.startswith("ru") else "en"
    path = PROMPT_DIR / f"signal_judge_{safe_lang}.txt"
    return path.read_text(encoding="utf-8").strip()


def _response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "signal_judge_output",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["relevance_score", "decision", "reason"],
                "properties": {
                    "relevance_score": {"type": "number", "minimum": 0, "maximum": 1},
                    "decision": {"type": "string", "enum": ["queue", "skip", "hide_source"]},
                    "reason": {"type": "string"},
                },
            },
        },
    }
