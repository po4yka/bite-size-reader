from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

# Known ISO 639-1 language codes (subset covering common languages)
KNOWN_LANG_CODES = {
    "af",
    "am",
    "ar",
    "az",
    "be",
    "bg",
    "bn",
    "bs",
    "ca",
    "cs",
    "cy",
    "da",
    "de",
    "el",
    "en",
    "es",
    "et",
    "eu",
    "fa",
    "fi",
    "fr",
    "ga",
    "gl",
    "gu",
    "ha",
    "he",
    "hi",
    "hr",
    "hu",
    "hy",
    "id",
    "is",
    "it",
    "ja",
    "ka",
    "kk",
    "km",
    "kn",
    "ko",
    "ku",
    "ky",
    "lb",
    "lo",
    "lt",
    "lv",
    "mk",
    "ml",
    "mn",
    "mr",
    "ms",
    "mt",
    "my",
    "nb",
    "ne",
    "nl",
    "nn",
    "no",
    "or",
    "pa",
    "pl",
    "ps",
    "pt",
    "ro",
    "ru",
    "rw",
    "sd",
    "si",
    "sk",
    "sl",
    "so",
    "sq",
    "sr",
    "sv",
    "sw",
    "ta",
    "te",
    "tg",
    "th",
    "tk",
    "tl",
    "tr",
    "uk",
    "ur",
    "uz",
    "vi",
    "zh",
}


def parse_vtt_file(
    path: Path, *, known_lang_codes: set[str] = KNOWN_LANG_CODES
) -> tuple[str, str | None]:
    """Parse a VTT subtitle file into plain text, and best-effort infer language."""
    lines: list[str] = []
    lang = None

    # Try to infer language code from filename suffix, e.g., .en.vtt
    parts = path.name.split(".")
    if len(parts) >= 3:
        candidate = parts[-2].lower()
        lang = candidate if candidate in known_lang_codes else None

    with path.open(encoding="utf-8") as f:
        for raw in f:
            stripped = raw.strip()
            if not stripped:
                continue
            if stripped.startswith("WEBVTT"):
                continue
            if "-->" in stripped:
                continue
            if stripped.isdigit():
                continue
            lines.append(stripped)

    text = " ".join(lines)
    return " ".join(text.split()), lang
