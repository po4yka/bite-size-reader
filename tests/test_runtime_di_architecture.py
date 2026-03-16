from __future__ import annotations

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
