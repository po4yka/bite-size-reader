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
    "!app/bootstrap/**",
    "!app/db/migrations/**",
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


def _run_rg(
    *, pattern: str, path: str = "app", fixed: bool = False, globs: list[str] | None = None
):
    glob_args: list[str] = []
    for glob in globs or []:
        glob_args.extend(["--glob", glob])
    cmd = ["rg", "-n"]
    if fixed:
        cmd.append("-F")
    cmd.extend([pattern, path, *glob_args])
    return subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.skipif(shutil.which("rg") is None, reason="rg is required for architecture guard")
def test_runtime_resource_construction_is_centralized_in_app_di() -> None:
    """Production runtime resources should only be assembled in app/di or CLI binaries."""
    for pattern in PATTERNS:
        result = _run_rg(pattern=pattern, fixed=True, globs=EXCLUDED_GLOBS)
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


@pytest.mark.skipif(shutil.which("rg") is None, reason="rg is required for architecture guard")
def test_removed_repository_port_layer_and_container_are_not_used() -> None:
    patterns = [
        "from app.adapters.repository_ports",
        "import app.adapters.repository_ports",
        "from app.di.container import",
        "Container(",
    ]
    for pattern in patterns:
        result = _run_rg(pattern=pattern, fixed=True)
        assert result.returncode in (0, 1)
        assert result.stdout.strip() == "", (
            f"found removed architecture surface for {pattern!r}:\n{result.stdout}"
        )


@pytest.mark.skipif(shutil.which("rg") is None, reason="rg is required for architecture guard")
def test_core_workflows_do_not_import_legacy_search_service_modules() -> None:
    patterns = [
        r"from app\.services\.(topic_search|summary_embedding_generator|vector_search_service|hybrid_search_service|related_reads_service|topic_search_utils)",
        r"import app\.services\.(topic_search|summary_embedding_generator|vector_search_service|hybrid_search_service|related_reads_service|topic_search_utils)",
    ]
    globs = [
        "!app/services/**",
        "!app/cli/**",
        "!app/application/services/topic_search_utils.py",
    ]
    for pattern in patterns:
        result = _run_rg(pattern=pattern, globs=globs)
        assert result.returncode in (0, 1)
        assert result.stdout.strip() == "", (
            f"found legacy search-service import still in production code for {pattern!r}:\n"
            f"{result.stdout}"
        )


@pytest.mark.skipif(shutil.which("rg") is None, reason="rg is required for architecture guard")
def test_core_workflows_do_not_construct_sqlite_repositories_outside_di() -> None:
    result = _run_rg(
        pattern=r"Sqlite[A-Za-z]+RepositoryAdapter\(",
        path="app",
        globs=[
            "app/api/services/**",
            "app/adapters/telegram/**",
            "app/application/**",
            "app/api/background_processor.py",
            "!app/api/services/collection_service.py",
        ],
    )
    assert result.returncode in (0, 1)
    assert result.stdout.strip() == "", (
        "found direct Sqlite repository construction outside app/di in core workflows:\n"
        f"{result.stdout}"
    )


@pytest.mark.skipif(shutil.which("rg") is None, reason="rg is required for architecture guard")
def test_p2_runtime_modules_do_not_import_app_di() -> None:
    result = _run_rg(
        pattern=r"from app\.di|import app\.di|app\.di\.",
        path="app",
        globs=[
            "app/adapters/**",
            "app/api/services/**",
            "app/api/background_processor.py",
            "app/db/**",
            "app/infrastructure/**",
            "!app/bootstrap/**",
        ],
    )
    assert result.returncode in (0, 1)
    assert result.stdout.strip() == "", (
        f"found forbidden app.di import in disallowed runtime package:\n{result.stdout}"
    )


@pytest.mark.skipif(shutil.which("rg") is None, reason="rg is required for architecture guard")
def test_p2_runtime_modules_do_not_use_runtime_builder_shortcuts() -> None:
    patterns = [
        r"build_[A-Za-z0-9_]+repository\(",
        r"build_[A-Za-z0-9_]+dependencies\(",
        r"build_runtime_database\(",
        r"get_current_api_runtime\(",
        r"resolve_api_runtime\(",
        r"build_scheduler_dependencies\(",
    ]
    globs = [
        "app/adapters/**",
        "app/api/services/**",
        "app/api/background_processor.py",
        "app/db/**",
        "app/infrastructure/**",
        "!app/bootstrap/**",
    ]
    for pattern in patterns:
        result = _run_rg(pattern=pattern, path="app", globs=globs)
        assert result.returncode in (0, 1)
        assert result.stdout.strip() == "", (
            f"found forbidden runtime builder shortcut for {pattern!r}:\n{result.stdout}"
        )
