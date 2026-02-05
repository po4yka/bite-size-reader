from __future__ import annotations

from typing import Any


def validate_model_name(model: str) -> str:
    """Validate model name for security and allow OpenRouter-style IDs."""
    if not model:
        msg = "Model name cannot be empty"
        raise ValueError(msg)
    if len(model) > 100:
        msg = "Model name too long"
        raise ValueError(msg)

    if ".." in model or "<" in model or ">" in model or "\\" in model:
        msg = "Model name contains invalid characters"
        raise ValueError(msg)

    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:/")
    if any(ch not in allowed for ch in model):
        msg = "Model name contains invalid characters"
        raise ValueError(msg)

    return model


def _ensure_api_key(value: str, *, name: str) -> str:
    if not value:
        msg = f"{name} API key is required"
        raise ValueError(msg)
    value = value.strip()
    if not value:
        msg = f"{name} API key is required"
        raise ValueError(msg)
    if len(value) > 500:
        msg = f"{name} API key appears to be too long"
        raise ValueError(msg)
    if any(char in value for char in [" ", "\n", "\t"]):
        msg = f"{name} API key contains invalid characters"
        raise ValueError(msg)
    return value


def _parse_allowed_user_ids(value: Any) -> tuple[int, ...]:
    if value in (None, ""):
        return ()
    values = value if isinstance(value, list | tuple) else str(value).split(",")

    user_ids: list[int] = []
    for piece in values:
        piece = str(piece).strip()
        if not piece:
            continue
        try:
            user_ids.append(int(piece))
        except ValueError:
            continue
    return tuple(user_ids)
