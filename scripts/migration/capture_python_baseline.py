#!/usr/bin/env python3
"""Capture M0 Python baseline metrics for parity suite.

Writes two artifacts:
- latest snapshot JSON (default: docs/migration/baseline_metrics.json)
- append-only history JSONL (default: docs/migration/baseline_metrics_history.jsonl)
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

_PARITY_SUITE_TIMEOUT_SEC = 30 * 60
_GIT_REV_TIMEOUT_SEC = 15


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="docs/migration/baseline_metrics.json",
        help="Path for latest baseline snapshot JSON.",
    )
    parser.add_argument(
        "--history",
        default="docs/migration/baseline_metrics_history.jsonl",
        help="Path for append-only JSONL run history.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    output_path = repo_root / args.output
    history_path = repo_root / args.history
    command = ["bash", "scripts/migration/run_parity_suite.sh"]

    start = time.perf_counter()
    proc = subprocess.run(
        command,
        cwd=repo_root,
        check=False,
        timeout=_PARITY_SUITE_TIMEOUT_SEC,
    )
    duration_s = time.perf_counter() - start
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)

    git_commit = os.getenv("GITHUB_SHA")
    if not git_commit:
        git_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            timeout=_GIT_REV_TIMEOUT_SEC,
        ).strip()

    payload = {
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "git_commit": git_commit,
        "runtime": "python",
        "suite": "m0_parity",
        "command": " ".join(command),
        "exit_code": proc.returncode,
        "wall_time_seconds": round(duration_s, 3),
        "cpu_user_seconds": round(usage.ru_utime, 3),
        "cpu_system_seconds": round(usage.ru_stime, 3),
        "max_rss_kb": usage.ru_maxrss,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=output_path.parent,
        prefix=f".{output_path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp.write(json.dumps(payload, indent=2) + "\n")
        temp_output = Path(tmp.name)
    temp_output.replace(output_path)

    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, separators=(",", ":")) + "\n")

    print(f"Wrote baseline snapshot to {output_path}")
    print(f"Appended baseline history to {history_path}")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
