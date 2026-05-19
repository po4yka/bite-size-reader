"""Enforce that .claude/skills and .codex/skills expose the same skill set.

A skill is a subdirectory containing a SKILL.md file. The two trees must
expose identical skill names; SKILL.md body contents are allowed to diverge
(each tool may need to phrase tool names or workflow details differently).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLAUDE_SKILLS = ROOT / ".claude" / "skills"
CODEX_SKILLS = ROOT / ".codex" / "skills"


def _skill_names(root: Path) -> set[str]:
    if not root.is_dir():
        return set()
    return {
        child.name for child in root.iterdir() if child.is_dir() and (child / "SKILL.md").is_file()
    }


def main() -> int:
    if not CLAUDE_SKILLS.is_dir():
        print(f"Missing directory: {CLAUDE_SKILLS}", file=sys.stderr)
        return 1
    if not CODEX_SKILLS.is_dir():
        print(f"Missing directory: {CODEX_SKILLS}", file=sys.stderr)
        return 1

    claude = _skill_names(CLAUDE_SKILLS)
    codex = _skill_names(CODEX_SKILLS)

    only_claude = sorted(claude - codex)
    only_codex = sorted(codex - claude)

    if not only_claude and not only_codex:
        print(f"Skills in sync ({len(claude)} skills).")
        return 0

    print("Skill directories are out of sync between .claude and .codex.", file=sys.stderr)
    if only_claude:
        print("\nIn .claude/skills but missing from .codex/skills:", file=sys.stderr)
        for name in only_claude:
            print(f"  - {name}", file=sys.stderr)
    if only_codex:
        print("\nIn .codex/skills but missing from .claude/skills:", file=sys.stderr)
        for name in only_codex:
            print(f"  - {name}", file=sys.stderr)
    print(
        "\nEach skill must exist as <name>/SKILL.md under BOTH trees. "
        "Body contents may differ; the directory set must match.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
