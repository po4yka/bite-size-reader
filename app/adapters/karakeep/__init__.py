"""Karakeep integration adapter for bookmark synchronization."""

from app.adapters.karakeep.client import KarakeepClient
from app.adapters.karakeep.sync_service import KarakeepSyncService

__all__ = ["KarakeepClient", "KarakeepSyncService"]
