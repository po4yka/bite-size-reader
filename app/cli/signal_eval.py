"""Signal-scoring eval export and precision helpers."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from app.config import DatabaseConfig
from app.db.session import Database
from app.infrastructure.persistence.repositories.signal_source_repository import (
    SignalSourceRepositoryAdapter,
)

RELEVANT_STATUSES = {"liked", "queued"}


def load_eval_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def compute_precision_at_k(rows: list[dict[str, Any]], *, k: int = 5) -> dict[str, int | float]:
    ranked = sorted(
        rows,
        key=lambda row: (
            int(row.get("rank") or 1_000_000),
            -float(row.get("final_score") or 0.0),
        ),
    )[:k]
    relevant = sum(1 for row in ranked if _is_relevant(row))
    evaluated = len(ranked)
    precision = relevant / evaluated if evaluated else 0.0
    return {"k": k, "evaluated": evaluated, "relevant": relevant, "precision": precision}


async def export_eval_set(
    *,
    database_dsn: str | None,
    output_path: Path,
    user_id: int,
    limit: int,
    status: str | None,
) -> int:
    db = Database(config=DatabaseConfig(dsn=database_dsn) if database_dsn else DatabaseConfig())
    try:
        repo = SignalSourceRepositoryAdapter(db)
        rows = await repo.async_list_user_signals(user_id, status=status, limit=limit)
        with output_path.open("w", encoding="utf-8") as handle:
            for idx, row in enumerate(rows, start=1):
                payload = {
                    "rank": idx,
                    "signal_id": row.get("id"),
                    "status": row.get("status"),
                    "final_score": row.get("final_score"),
                    "feed_item_title": row.get("feed_item_title"),
                    "feed_item_url": row.get("feed_item_url"),
                    "source_title": row.get("source_title"),
                    "topic_name": row.get("topic_name"),
                    "relevant": _is_relevant(row),
                }
                handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        return len(rows)
    finally:
        await db.dispose()


def _is_relevant(row: dict[str, Any]) -> bool:
    if "relevant" in row:
        return bool(row["relevant"])
    return str(row.get("status") or "").lower() in RELEVANT_STATUSES


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ratatoskr-signal-eval")
    subcommands = parser.add_subparsers(dest="command", required=True)

    export = subcommands.add_parser("export", help="Export ranked signals as JSONL for labeling")
    export.add_argument("--dsn", default=None, help="PostgreSQL DSN (default: DATABASE_URL)")
    export.add_argument("--output", required=True, type=Path)
    export.add_argument("--user-id", required=True, type=int)
    export.add_argument("--limit", type=int, default=100)
    export.add_argument("--status", default=None)

    precision = subcommands.add_parser("precision", help="Compute precision@k from JSONL")
    precision.add_argument("--input", required=True, type=Path)
    precision.add_argument("--k", type=int, default=5)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "export":
        count = asyncio.run(
            export_eval_set(
                database_dsn=args.dsn,
                output_path=args.output,
                user_id=args.user_id,
                limit=args.limit,
                status=args.status,
            )
        )
        print(json.dumps({"exported": count, "output": str(args.output)}))
        return 0

    rows = load_eval_rows(args.input)
    print(json.dumps(compute_precision_at_k(rows, k=args.k)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
