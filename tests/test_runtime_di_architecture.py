from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "app"
EXCLUDED_GLOBS = [
    "!app/di/**",
    "!app/cli/**",
    "!app/cli/migrations/**",
]
PATTERNS = [
    "DatabaseSessionManager(",
    "LLMClientFactory.create_from_config(",
    "ContentScraperFactory.create_from_config(",
    "ResponseFormatter(",
    "LocalTopicSearchService(",
    "SummaryEmbeddingGenerator(",
    "ChromaVectorStore(",
]
FORMATTER_PRIVATE_PATTERNS = {
    "response_formatter.sender": re.compile(r"\b[\w.]*response_formatter\.sender\b"),
    "response_formatter.notifications": re.compile(r"\b[\w.]*response_formatter\.notifications\b"),
    "response_formatter.summaries": re.compile(r"\b[\w.]*response_formatter\.summaries\b"),
    "response_formatter.database": re.compile(r"\b[\w.]*response_formatter\.database\b"),
    "response_formatter._summary_presenter": re.compile(
        r"\b[\w.]*response_formatter\._summary_presenter\b"
    ),
    "response_formatter._notification_formatter": re.compile(
        r"\b[\w.]*response_formatter\._notification_formatter\b"
    ),
    "response_formatter._response_sender": re.compile(
        r"\b[\w.]*response_formatter\._response_sender\b"
    ),
    "response_formatter._safe_reply_func": re.compile(
        r"\b[\w.]*response_formatter\._safe_reply_func\b"
    ),
    "response_formatter._reply_json_func": re.compile(
        r"\b[\w.]*response_formatter\._reply_json_func\b"
    ),
}


@pytest.mark.skipif(shutil.which("rg") is None, reason="rg is required for architecture guard")
def test_runtime_resource_construction_is_centralized_in_app_di() -> None:
    """Production runtime resources should only be assembled in app/di or CLI binaries."""
    for pattern in PATTERNS:
        glob_args: list[str] = []
        for glob in EXCLUDED_GLOBS:
            glob_args.extend(["--glob", glob])
        cmd = ["rg", "-n", "-F", pattern, "app", *glob_args]
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode in (0, 1)
        assert result.stdout.strip() == "", (
            f"found forbidden runtime construction for {pattern!r}:\n{result.stdout}"
        )


def test_formatter_private_surfaces_are_not_used_outside_formatting_package() -> None:
    """Production code should use ResponseFormatter's public API only."""
    excluded = {
        PROJECT_ROOT / "app" / "adapters" / "external" / "response_formatter.py",
    }

    for path in APP_ROOT.rglob("*.py"):
        if "app/adapters/external/formatting/" in path.as_posix():
            continue
        if path in excluded:
            continue

        text = path.read_text()
        offenders = [
            label for label, pattern in FORMATTER_PRIVATE_PATTERNS.items() if pattern.search(text)
        ]
        assert offenders == [], f"found forbidden formatter surface usage in {path}:\n" + "\n".join(
            offenders
        )
