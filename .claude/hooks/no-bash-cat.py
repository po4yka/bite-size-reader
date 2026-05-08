#!/usr/bin/env python3
"""PreToolUse(Bash) hook: redirect file-viewing commands to the Read tool.

Why this exists: when the model uses `cat path/to/file` (or `head`/`tail`/
`sed -n`) via Bash, the Read-tool tracking that the Edit tool depends on is
NOT updated. A subsequent Edit on that file fails with
"File must be read first", which has caused autonomous loops to stop. By
denying these specific Bash invocations, the model is forced to use the Read
tool, which both keeps Edit's invariant satisfied and avoids the stall.

Allowed (returns exit 0, no decision):
  - echo x | cat               (no positional file)
  - cat <<EOF\n...\nEOF        (heredoc, no file path token)
  - tail -f                    (no positional path)
  - git log | head -20         (-20 is a flag-like, not a path)

Blocked:
  - cat foo.py                 (extension-bearing positional)
  - head -n 50 path/to/file
  - tail -f /var/log/foo
  - sed -n '1,10p' app/main.py
"""
from __future__ import annotations

import json
import shlex
import sys

VIEWERS = {"cat", "head", "tail", "sed", "less", "more", "bat"}

KNOWN_BARE_FILES = {
    "Makefile", "GNUmakefile", "BSDmakefile",
    "Dockerfile", "Containerfile",
    "LICENSE", "COPYING", "NOTICE", "AUTHORS",
    "README", "CHANGELOG", "HISTORY", "TODO",
    "MANIFEST", "INSTALL", "VERSION",
    "Procfile", "Vagrantfile", "Rakefile", "Gemfile", "Brewfile",
}


def looks_like_path(tok: str) -> bool:
    if tok in ("-", "/dev/stdin", "/dev/null"):
        return False
    if tok.startswith(("-", "$", "<", ">", "`")):
        return False
    if tok.startswith(("'", '"')):
        return False
    if "/" in tok or "." in tok:
        return True
    return tok in KNOWN_BARE_FILES


def first_positional(viewer: str, args: list[str]) -> str | None:
    """Find the first positional arg in `args` that looks like a file path,
    skipping flags that consume an argument."""
    skip_next = False
    saw_sed_script = False
    for t in args:
        if skip_next:
            skip_next = False
            continue
        if t.startswith("-") and len(t) > 1:
            if viewer in ("head", "tail") and t in ("-n", "-c"):
                skip_next = True
            elif viewer == "sed" and t in ("-e", "-f", "-i"):
                skip_next = True
            continue
        if viewer == "sed" and not saw_sed_script:
            saw_sed_script = True
            continue
        if looks_like_path(t):
            return t
    return None


def detect(cmd: str) -> tuple[str | None, str | None]:
    """Only inspect the very first command token. Avoids false positives from
    quoted text or piped tail-stages — both common in `git commit -m "..."`,
    heredocs, and complex pipelines. The failure mode this hook exists to
    prevent (model invokes `cat path` instead of Read) is always the LEAD
    command, so this trade-off is safe."""
    head_str = cmd.lstrip().lstrip("(").lstrip()
    if not head_str:
        return None, None
    try:
        toks = shlex.split(head_str, comments=False, posix=True)
    except ValueError:
        # Malformed quoting — let bash decide; don't block.
        return None, None
    if not toks:
        return None, None
    head = toks[0]
    if head not in VIEWERS:
        return None, None
    path = first_positional(head, toks[1:])
    if path:
        return head, path
    return None, None


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)
    tool_input = data.get("tool_input") or data.get("tool_args") or {}
    cmd = tool_input.get("command", "") or ""
    viewer, path = detect(cmd)
    if viewer:
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"Use the Read tool to view `{path}` — not Bash `{viewer}`. "
                    "Bash file-viewers don't update Edit's read-tracking, which "
                    "causes 'File must be read first' errors on later Edits. "
                    "Pipelines without a positional file (e.g. `cmd | head -20`) "
                    "are unaffected by this hook."
                ),
            }
        }
        print(json.dumps(out))
    sys.exit(0)


if __name__ == "__main__":
    main()
