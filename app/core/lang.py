from __future__ import annotations

import re

LANG_EN = "en"
LANG_RU = "ru"
LANG_AUTO = "auto"


def detect_language(text: str) -> str:
    """Very lightweight language detection between Russian and English.

    If the text contains any Cyrillic characters, returns 'ru', else 'en'.
    """
    if not text:
        return LANG_EN
    if re.search(r"[\u0400-\u04FF]", text):
        return LANG_RU
    return LANG_EN


def choose_language(preferred: str, detected: str) -> str:
    preferred = (preferred or LANG_AUTO).lower()
    detected = (detected or LANG_EN).lower()
    if preferred in (LANG_EN, LANG_RU):
        return preferred
    return detected if detected in (LANG_EN, LANG_RU) else LANG_EN
