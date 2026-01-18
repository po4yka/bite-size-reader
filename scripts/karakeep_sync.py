#!/usr/bin/env python3
"""Cron-triggered Karakeep sync script.

Run this script via cron to automatically sync between BSR and Karakeep.

Example crontab entry (every 6 hours):
    0 */6 * * * cd /home/po4yka/bite-size-reader && .venv/bin/python scripts/karakeep_sync.py >> /var/log/karakeep_sync.log 2>&1

Usage:
    python scripts/karakeep_sync.py [--user-id USER_ID] [--limit LIMIT] [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("karakeep_sync")


async def run_sync(
    user_id: int | None = None, limit: int | None = None, dry_run: bool = False
) -> int:
    """Run Karakeep sync.

    Args:
        user_id: User ID for Karakeep→BSR sync
        limit: Maximum items per direction
        dry_run: If True, only show what would be synced

    Returns:
        Exit code (0 for success, 1 for error)
    """
    from app.adapters.karakeep import KarakeepSyncService
    from app.config import load_config
    from app.db.session import DatabaseSessionManager
    from app.infrastructure.persistence.sqlite.repositories.karakeep_sync_repository import (
        SqliteKarakeepSyncRepositoryAdapter,
    )

    try:
        # Load configuration
        cfg = load_config(allow_stub_telegram=True)

        if not cfg.karakeep.enabled:
            logger.warning("Karakeep sync is disabled. Set KARAKEEP_ENABLED=true to enable.")
            return 1

        if not cfg.karakeep.api_key:
            logger.error("Karakeep API key not configured. Set KARAKEEP_API_KEY.")
            return 1

        # Initialize database session
        db = DatabaseSessionManager(cfg.runtime.db_path)
        db.migrate()

        logger.info(
            "Starting Karakeep sync",
            extra={
                "api_url": cfg.karakeep.api_url,
                "user_id": user_id,
                "limit": limit,
                "dry_run": dry_run,
            },
        )

        # Create sync service with repository
        karakeep_repo = SqliteKarakeepSyncRepositoryAdapter(db)
        service = KarakeepSyncService(
            api_url=cfg.karakeep.api_url,
            api_key=cfg.karakeep.api_key,
            sync_tag=cfg.karakeep.sync_tag,
            repository=karakeep_repo,
        )

        if dry_run:
            logger.info("DRY RUN - no changes will be made")
            preview = await service.preview_sync(user_id=user_id, limit=limit)

            print("\n=== Karakeep Sync Preview (DRY RUN) ===\n")

            # BSR → Karakeep
            bsr_to_kk = preview["bsr_to_karakeep"]
            print("BSR -> Karakeep:")
            print(f"  Would sync: {len(bsr_to_kk['would_sync'])} items")
            print(f"  Would skip: {bsr_to_kk['would_skip']} (already synced)")
            print(f"  Already in Karakeep: {len(bsr_to_kk['already_exists_in_karakeep'])}")
            if bsr_to_kk["would_sync"]:
                print("\n  Items that would be synced:")
                for item in bsr_to_kk["would_sync"][:10]:
                    title = item.get("title", "")[:50] or "(no title)"
                    print(f"    - [#{item['summary_id']}] {title}...")
                    print(f"      URL: {item['url'][:60]}...")
                if len(bsr_to_kk["would_sync"]) > 10:
                    print(f"    ... and {len(bsr_to_kk['would_sync']) - 10} more")

            print()

            # Karakeep → BSR
            kk_to_bsr = preview["karakeep_to_bsr"]
            print("Karakeep -> BSR:")
            print(f"  Would sync: {len(kk_to_bsr['would_sync'])} items")
            print(f"  Would skip: {kk_to_bsr['would_skip']} (already synced)")
            print(f"  Already in BSR: {len(kk_to_bsr['already_exists_in_bsr'])}")
            if kk_to_bsr["would_sync"]:
                print("\n  Items that would be synced:")
                for item in kk_to_bsr["would_sync"][:10]:
                    title = (item.get("title") or "(no title)")[:50]
                    print(f"    - [{item['karakeep_id']}] {title}")
                    print(f"      URL: {item['url'][:60]}...")
                if len(kk_to_bsr["would_sync"]) > 10:
                    print(f"    ... and {len(kk_to_bsr['would_sync']) - 10} more")

            # Errors
            if preview["errors"]:
                print(f"\nErrors ({len(preview['errors'])}):")
                for err in preview["errors"]:
                    print(f"  - {err}")

            print("\n=== End of Preview ===")
            print("Run without --dry-run to execute the sync.")
            return 0

        # Run actual sync (service already created above)
        result = await service.run_full_sync(user_id=user_id, limit=limit)

        # Log results
        logger.info(
            "Karakeep sync completed",
            extra={
                "bsr_to_karakeep_synced": result.bsr_to_karakeep.items_synced,
                "bsr_to_karakeep_skipped": result.bsr_to_karakeep.items_skipped,
                "bsr_to_karakeep_failed": result.bsr_to_karakeep.items_failed,
                "karakeep_to_bsr_synced": result.karakeep_to_bsr.items_synced,
                "karakeep_to_bsr_skipped": result.karakeep_to_bsr.items_skipped,
                "karakeep_to_bsr_failed": result.karakeep_to_bsr.items_failed,
                "duration_seconds": result.total_duration_seconds,
            },
        )

        # Print summary
        print("\n=== Karakeep Sync Summary ===")
        print(
            f"BSR → Karakeep: {result.bsr_to_karakeep.items_synced} synced, "
            f"{result.bsr_to_karakeep.items_skipped} skipped, "
            f"{result.bsr_to_karakeep.items_failed} failed"
        )
        print(
            f"Karakeep → BSR: {result.karakeep_to_bsr.items_synced} synced, "
            f"{result.karakeep_to_bsr.items_skipped} skipped, "
            f"{result.karakeep_to_bsr.items_failed} failed"
        )
        print(f"Duration: {result.total_duration_seconds:.1f}s")

        # Report errors
        all_errors = result.bsr_to_karakeep.errors + result.karakeep_to_bsr.errors
        if all_errors:
            print(f"\nErrors ({len(all_errors)}):")
            for err in all_errors[:10]:
                print(f"  - {err}")

        return 0 if not all_errors else 1

    except Exception as e:
        logger.exception("Karakeep sync failed")
        print(f"\nERROR: {e}")
        return 1


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Sync articles between BSR and Karakeep")
    parser.add_argument(
        "--user-id",
        type=int,
        default=None,
        help="User ID for Karakeep→BSR sync (defaults to first allowed user)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum items to sync per direction",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be synced without making changes",
    )
    args = parser.parse_args()

    # If no user_id provided, try to get from ALLOWED_USER_IDS
    user_id = args.user_id
    if user_id is None:
        allowed_ids = os.getenv("ALLOWED_USER_IDS", "")
        if allowed_ids:
            try:
                user_id = int(allowed_ids.split(",")[0].strip())
            except (ValueError, IndexError):
                pass

    exit_code = asyncio.run(run_sync(user_id=user_id, limit=args.limit, dry_run=args.dry_run))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
