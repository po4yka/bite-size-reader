"""Karakeep integration adapter for bookmark synchronization."""

from app.adapters.karakeep.client import KarakeepClient
from app.adapters.karakeep.sync.service import KarakeepSyncService

__all__ = ["KarakeepClient", "KarakeepSyncService"]
