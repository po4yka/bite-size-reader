"""Compatibility re-exports for legacy summary route imports."""

from app.api.routers.content.summaries import get_summary, get_summary_by_url, router

__all__ = ["get_summary", "get_summary_by_url", "router"]
