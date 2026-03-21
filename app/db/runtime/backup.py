"""Database backup service."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class DatabaseBackupService:
    """Create and verify SQLite backup copies."""

    def __init__(self, *, path: str, connect: Any, logger: Any) -> None:
        self._path = path
        self._connect = connect
        self._logger = logger

    def create_backup_copy(self, dest_path: str) -> Path:
        if self._path == ":memory:":
            raise ValueError("Cannot create a backup for an in-memory database")

        source = Path(self._path)
        if not source.exists():
            raise FileNotFoundError(f"Database file not found at {self._path}")

        destination = Path(dest_path)
        destination.parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as conn, sqlite3.connect(str(destination)) as dest_conn:
            conn.backup(dest_conn)
            dest_conn.commit()

            try:
                cursor = dest_conn.execute("PRAGMA quick_check")
                row = cursor.fetchone()
                backup_check = row[0] if row else "unknown"
                backup_ok = backup_check == "ok"
            except sqlite3.DatabaseError as check_err:
                backup_ok = False
                backup_check = str(check_err)

            if backup_ok:
                self._logger.info(
                    "db_backup_integrity_verified",
                    extra={"dest": self._mask_path(str(destination))},
                )
            else:
                self._logger.warning(
                    "db_backup_integrity_failed",
                    extra={
                        "dest": self._mask_path(str(destination)),
                        "quick_check_result": backup_check,
                    },
                )

        self._logger.info(
            "db_backup_copy_created",
            extra={
                "source": self._mask_path(str(source)),
                "dest": self._mask_path(str(destination)),
            },
        )
        return destination

    @staticmethod
    def _mask_path(path: str) -> str:
        try:
            p = Path(path)
            if not p.name:
                return str(p)
            parent = p.parent.name
            if parent:
                return f".../{parent}/{p.name}"
            return p.name
        except (OSError, ValueError, AttributeError):
            return "..."
