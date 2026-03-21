"""Pure domain services for tag business logic.

These functions contain no DB access -- they operate on values only.
"""

import re

_MAX_TAG_NAME_LENGTH = 100
_FORBIDDEN_CHARS_PATTERN = re.compile(r"[#@]")


def normalize_tag_name(name: str) -> str:
    """Lowercase, strip whitespace, collapse internal spaces."""
    return " ".join(name.lower().strip().split())


def validate_tag_name(name: str) -> tuple[bool, str | None]:
    """Validate tag name. Returns (is_valid, error_message)."""
    normalized = normalize_tag_name(name)
    if not normalized:
        return False, "tag name cannot be empty"
    if len(normalized) > _MAX_TAG_NAME_LENGTH:
        return False, f"tag name must be at most {_MAX_TAG_NAME_LENGTH} characters"
    if _FORBIDDEN_CHARS_PATTERN.search(normalized):
        return False, "tag name cannot contain # or @ characters"
    return True, None


def validate_tag_color(color: str | None) -> tuple[bool, str | None]:
    """Validate hex color format (#RRGGBB). None is valid."""
    if color is None:
        return True, None
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        return False, "color must be in #RRGGBB hex format"
    return True, None
