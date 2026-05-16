"""CLI tool: re-encrypt all UserGitHubIntegration tokens under the primary Fernet key.

Run this after adding a new GITHUB_TOKEN_ENCRYPTION_KEY and moving the old key to
GITHUB_TOKEN_PREVIOUS_KEYS. Once complete, the old key can be safely removed.

Usage:
    python -m app.cli.rotate_github_tokens [--dry-run] [--user-id ID] [--log-level LEVEL]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.cli._runtime import prepare_config
from app.core.logging_utils import get_logger, setup_json_logging
from app.db.models.repository import UserGitHubIntegration
from app.di.database import build_runtime_database
from app.security.token_crypto import InvalidEncryptedTokenError, decrypt_token, encrypt_token

if TYPE_CHECKING:
    from app.db.session import Database

logger = get_logger(__name__)

__all__ = ["ReencryptResult", "main", "reencrypt_all_tokens"]


@dataclass(frozen=True)
class ReencryptResult:
    processed: int
    reencrypted: int
    failed: int


async def reencrypt_all_tokens(
    db: Database,
    *,
    dry_run: bool = False,
    user_id: int | None = None,
) -> ReencryptResult:
    """Re-encrypt every integration token with the current primary key.

    Decryption uses MultiFernet (primary + previous keys); encryption uses primary only.
    Rows that cannot be decrypted are counted as *failed* and logged — the loop continues.
    """
    async with db.session() as session:
        stmt = select(UserGitHubIntegration)
        if user_id is not None:
            stmt = stmt.where(UserGitHubIntegration.user_id == user_id)
        result = await session.execute(stmt)
        rows: list[UserGitHubIntegration] = list(result.scalars().all())

    processed = reencrypted = failed = 0

    for row in rows:
        processed += 1
        try:
            plaintext = decrypt_token(row.encrypted_token)
            new_ct = encrypt_token(plaintext)
            if not dry_run:
                async with db.transaction() as txn:
                    fresh = await txn.get(UserGitHubIntegration, row.id)
                    if fresh is not None:
                        fresh.encrypted_token = new_ct
                row.encrypted_token = new_ct  # reflect for callers / tests
            reencrypted += 1
            logger.info(
                "token_reencrypted",
                extra={"user_id": row.user_id, "dry_run": dry_run},
            )
        except InvalidEncryptedTokenError:
            failed += 1
            logger.error(
                "token_reencrypt_failed_undecryptable",
                extra={"user_id": row.user_id},
            )

    return ReencryptResult(processed=processed, reencrypted=reencrypted, failed=failed)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Re-encrypt all GitHub integration tokens under the primary Fernet key. "
            "Run after rotating GITHUB_TOKEN_ENCRYPTION_KEY."
        ),
        allow_abbrev=False,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Report would-be changes without writing to the database.",
    )
    parser.add_argument(
        "--user-id",
        type=int,
        default=None,
        help="Restrict re-encryption to this Telegram user_id.",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Path to a .env file with environment variables.",
    )
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> None:
    cfg = prepare_config(args)
    setup_json_logging(cfg.runtime.log_level)

    db = build_runtime_database(cfg, migrate=False)
    result = await reencrypt_all_tokens(db, dry_run=args.dry_run, user_id=args.user_id)

    import json

    try:
        import orjson

        print(orjson.dumps(asdict(result), option=orjson.OPT_INDENT_2).decode())
    except ImportError:
        print(json.dumps(asdict(result), indent=2))

    if result.failed:
        sys.exit(1)


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python -m app.cli.rotate_github_tokens``."""
    args = parse_args(argv)
    try:
        asyncio.run(_run(args))
    except SystemExit as exc:
        code = exc.code
        return int(code) if isinstance(code, int) else 1
    except KeyboardInterrupt:  # pragma: no cover
        return 1
    except Exception as exc:
        logger.exception("rotate_github_tokens_failed", exc_info=exc)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
