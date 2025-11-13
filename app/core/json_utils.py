from __future__ import annotations

import json
import re
from typing import Any


def extract_json(text: str) -> dict[str, Any] | None:
    """Extract a JSON object from a string.

    Attempts to recover from common issues such as Markdown code fences,
    extra explanatory text, trailing commas, or missing closing braces without
    making additional LLM calls. Returns the parsed object or ``None`` if
    parsing fails.
    """
    if not isinstance(text, str):
        return None

    candidate = text.strip()
    if not candidate:
        return None

    # Handle markdown-style code fences: ```json ... ```
    fence_match = re.search(r"```(?:json)?\s*(.*?)```", candidate, flags=re.IGNORECASE | re.DOTALL)
    candidate = fence_match.group(1).strip() if fence_match else candidate.strip("`")

    # Remove leading "json" language hint if present
    candidate = re.sub(r"^json\s*", "", candidate, flags=re.IGNORECASE)

    def _try_parse(raw: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(raw)
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None

    parsed = _try_parse(candidate)
    if parsed is not None:
        return parsed

    # Attempt to locate the first JSON object within the candidate string
    start = candidate.find("{")
    if start == -1:
        return None
    end = candidate.rfind("}")
    snippet = candidate[start:] if end == -1 or end <= start else candidate[start:end + 1]
    parsed = _try_parse(snippet)
    if parsed is not None:
        return parsed

    # Remove dangling trailing commas
    snippet = re.sub(r",\s*([}\]])", r"\1", snippet)
    parsed = _try_parse(snippet)
    if parsed is not None:
        return parsed

    # Balance braces if the response was truncated near the end
    brace_diff = snippet.count("{") - snippet.count("}")
    if brace_diff > 0:
        snippet = snippet + ("}" * brace_diff)
        parsed = _try_parse(snippet)
        if parsed is not None:
            return parsed

    return None
