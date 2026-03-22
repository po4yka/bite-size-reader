from __future__ import annotations

import ast
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
ROOT_SQLITE_REPOSITORY_MODULES = [
    APP_ROOT
    / "infrastructure"
    / "persistence"
    / "sqlite"
    / "repositories"
    / "request_repository.py",
    APP_ROOT
    / "infrastructure"
    / "persistence"
    / "sqlite"
    / "repositories"
    / "summary_repository.py",
    APP_ROOT
    / "infrastructure"
    / "persistence"
    / "sqlite"
    / "repositories"
    / "collection_repository.py",
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
FORMATTER_PRIVATE_MODULE_PATTERNS = [
    re.compile(r"from app\.adapters\.external\.formatting\._response_sender_"),
    re.compile(r"import app\.adapters\.external\.formatting\._response_sender_"),
    re.compile(
        r"from app\.adapters\.external\.formatting\.summary\.(presenter_context|summary_blocks|followup_presenters|structured_summary_flow)"
    ),
    re.compile(
        r"import app\.adapters\.external\.formatting\.summary\.(presenter_context|summary_blocks|followup_presenters|structured_summary_flow)"
    ),
]


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


def _parse_python(path: Path) -> ast.Module:
    return ast.parse(path.read_text(), filename=str(path))


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


def test_formatter_private_modules_are_not_imported_outside_formatting_package() -> None:
    """Production code should import only formatter public modules/protocols."""
    for path in APP_ROOT.rglob("*.py"):
        if "app/adapters/external/formatting/" in path.as_posix():
            continue
        if path == APP_ROOT / "adapters" / "external" / "response_formatter.py":
            continue
        text = path.read_text()
        offenders = [
            pattern.pattern for pattern in FORMATTER_PRIVATE_MODULE_PATTERNS if pattern.search(text)
        ]
        assert offenders == [], (
            f"found forbidden formatter private import in {path}:\n" + "\n".join(offenders)
        )


def test_formatter_concrete_root_modules_remain_thin_shells() -> None:
    """Concrete formatter roots should only expose construction and public delegation."""
    module_expectations = {
        APP_ROOT / "adapters" / "external" / "formatting" / "response_sender.py": (
            "ResponseSenderImpl"
        ),
        APP_ROOT / "adapters" / "external" / "formatting" / "summary_presenter.py": (
            "SummaryPresenterImpl"
        ),
    }

    for path, class_name in module_expectations.items():
        tree = _parse_python(path)
        module_functions = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
        assert module_functions == [], (
            f"{path} should not define module-level helpers: {module_functions}"
        )

        classes = [
            node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name
        ]
        assert len(classes) == 1, f"{path} should define exactly one {class_name}"
        methods = [
            node.name
            for node in classes[0].body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        private_methods = [name for name in methods if name.startswith("_") and name != "__init__"]
        assert private_methods == [], (
            f"{path} should not define private helper methods in {class_name}: {private_methods}"
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


@pytest.mark.skipif(shutil.which("rg") is None, reason="rg is required for architecture guard")
def test_production_code_does_not_import_root_application_ports_facade() -> None:
    patterns = [
        "from app.application.ports import",
        "import app.application.ports",
    ]
    for pattern in patterns:
        result = _run_rg(pattern=pattern, path="app", fixed=True)
        assert result.returncode in (0, 1)
        assert result.stdout.strip() == "", (
            f"found forbidden root ports facade import in production code for {pattern!r}:\n"
            f"{result.stdout}"
        )


@pytest.mark.skipif(shutil.which("rg") is None, reason="rg is required for architecture guard")
def test_production_code_does_not_import_response_formatter_root_facade() -> None:
    result = _run_rg(
        pattern="from app.adapters.external.response_formatter import ResponseFormatter",
        path="app",
        fixed=True,
        globs=[
            "!app/di/shared.py",
            "!app/adapters/external/response_formatter.py",
        ],
    )
    assert result.returncode in (0, 1)
    assert result.stdout.strip() == "", (
        "found forbidden ResponseFormatter root facade import outside DI compatibility layer:\n"
        f"{result.stdout}"
    )


def test_sqlite_repository_root_modules_are_thin_and_model_free() -> None:
    for path in ROOT_SQLITE_REPOSITORY_MODULES:
        module = _parse_python(path)

        imports_db_models = False
        for node in module.body:
            if isinstance(node, ast.Import):
                imports_db_models = imports_db_models or any(
                    alias.name == "app.db.models" for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                imports_db_models = imports_db_models or node.module == "app.db.models"
        assert not imports_db_models, f"{path} must not import app.db.models directly"

        top_level_functions = [
            node
            for node in module.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        assert top_level_functions == [], f"{path} must not define top-level helper functions"

        class_defs = [node for node in module.body if isinstance(node, ast.ClassDef)]
        assert len(class_defs) == 1, f"{path} must expose exactly one root adapter class"

        class_methods = [
            node
            for node in class_defs[0].body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        assert class_methods == [], f"{path} must remain a thin assembly shell"


@pytest.mark.skipif(shutil.which("rg") is None, reason="rg is required for architecture guard")
def test_private_sqlite_repository_modules_are_not_imported_outside_repository_package() -> None:
    patterns = [
        r"from app\.infrastructure\.persistence\.sqlite\.repositories\._",
        r"import app\.infrastructure\.persistence\.sqlite\.repositories\._",
    ]
    for pattern in patterns:
        result = _run_rg(
            pattern=pattern,
            path="app",
            globs=["!app/infrastructure/persistence/sqlite/repositories/**"],
        )
        assert result.returncode in (0, 1)
        assert result.stdout.strip() == "", (
            f"found private SQLite repository module import outside repository package for {pattern!r}:\n"
            f"{result.stdout}"
        )
