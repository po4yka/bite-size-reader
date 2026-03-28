from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

TRACKED_ROOT_ALLOWLIST = {
    ".agent",
    ".bandit",
    ".claude",
    ".continue",
    ".cursor",
    ".dockerignore",
    ".env.example",
    ".github",
    ".gitignore",
    ".gitleaks.toml",
    ".markdownlint-cli2.yaml",
    ".pip-audit-ignore.txt",
    ".pre-commit-config.yaml",
    ".python-version",
    "AGENTS.md",
    "app",
    "bot.py",
    "CHANGELOG.md",
    "CLAUDE.md",
    "clients",
    "docs",
    "integrations",
    "LICENSE",
    "Makefile",
    "ops",
    "pyproject.toml",
    "README.md",
    "requirements-all.txt",
    "requirements-dev.txt",
    "requirements.txt",
    "skills-lock.json",
    "tests",
    "tools",
    "uv.lock",
}

BANNED_ROOT_PATHS = {
    "frontend",
    ".desloppify_t2.json",
    ".desloppify_t2_latest.json",
    "security-audit-report.md",
    "security-audit-report.pdf",
    "requirements-tests.txt",
    ".coverage",
    "coverage.json",
    "coverage.xml",
    "htmlcov",
    "debug_fav.log",
    "error.log",
    "traceback.log",
}


def _tracked_root_entries() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "--stage"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    entries: set[str] = set()
    for line in result.stdout.splitlines():
        path = line.split(maxsplit=3)[-1]
        if "/" in path:
            entries.add(path.split("/", 1)[0])
        else:
            entries.add(path)
    return entries


def _find_banned_root_paths() -> list[str]:
    found: list[str] = []
    for name in sorted(BANNED_ROOT_PATHS):
        if (ROOT / name).exists():
            found.append(name)
    return found


def _scan_outdated_paths() -> list[str]:
    patterns = (
        r"(^|[^A-Za-z0-9_./-])FRONTEND\.md([^A-Za-z0-9_./-]|$)",
        r"(^|[^A-Za-z0-9_./-])cd web([^A-Za-z0-9_./-]|$)",
        r"(^|[^A-Za-z0-9_./-])working-directory:\s*web([^A-Za-z0-9_./-]|$)",
        r"(^|[^A-Za-z0-9_./-])/frontend([^A-Za-z0-9_./-]|$)",
    )
    cmd = [
        "rg",
        "-n",
        "-e",
        patterns[0],
        "-e",
        patterns[1],
        "-e",
        patterns[2],
        "-e",
        patterns[3],
        "README.md",
        "AGENTS.md",
        "CLAUDE.md",
        ".github",
        "docs",
        "clients",
        "ops",
        "tools",
        "tests",
        "Makefile",
        ".gitignore",
        "-g",
        "!tools/scripts/check_root_hygiene.py",
        "-g",
        "!docs/plans/**",
        "-g",
        "!docs/reports/**",
        "-g",
        "!.claude/**",
    ]
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 1:
        return []
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "rg failed")
    return result.stdout.splitlines()


def main() -> int:
    tracked = _tracked_root_entries()
    unexpected = sorted(tracked - TRACKED_ROOT_ALLOWLIST)
    missing = sorted(TRACKED_ROOT_ALLOWLIST - tracked)
    banned = _find_banned_root_paths()
    stale = _scan_outdated_paths()

    errors: list[str] = []
    if unexpected:
        errors.append("Unexpected tracked root entries: " + ", ".join(unexpected))
    if missing:
        errors.append("Missing tracked root entries: " + ", ".join(missing))
    if banned:
        errors.append("Banned root paths present: " + ", ".join(banned))
    if stale:
        errors.append("Outdated path references found:\n" + "\n".join(stale))

    if errors:
        print("Root hygiene check failed.", file=sys.stderr)
        print("\n\n".join(errors), file=sys.stderr)
        return 1

    print("Root hygiene check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
