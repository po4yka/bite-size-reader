"""Token counting utilities for LLM content budgeting."""

from __future__ import annotations

from app.core.logging_utils import get_logger

logger = get_logger(__name__)

_encoder = None
_encoder_loaded = False


def _get_encoder():
    """Lazily load tiktoken encoder. Returns None if tiktoken unavailable."""
    global _encoder, _encoder_loaded
    if _encoder_loaded:
        return _encoder
    _encoder_loaded = True
    try:
        import tiktoken

        _encoder = tiktoken.get_encoding("cl100k_base")
    except (ImportError, AttributeError, ValueError, KeyError, RuntimeError):
        logger.debug("encoder package unavailable, using heuristic budget estimation")
        _encoder = None
    return _encoder


def count_tokens(text: str) -> int:
    """Count tokens in text using tiktoken if available, else heuristic.

    Uses cl100k_base encoding (GPT-4 / most modern models). Falls back
    to len(text) // 4 which is more accurate than the previous //3 heuristic.

    Args:
        text: Input text to count tokens for.

    Returns:
        Estimated token count.
    """
    enc = _get_encoder()
    if enc is not None:
        try:
            return len(enc.encode(text))
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return max(1, len(text) // 4)
    # Fallback: ~4 chars per token for English text
    return max(1, len(text) // 4)
