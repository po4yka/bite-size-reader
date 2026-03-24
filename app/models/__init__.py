"""Deprecated compatibility facade for adapter/infrastructure data models.

Canonical import path: ``app.adapter_models``.

This package remains only to avoid breaking older imports while the codebase
finishes migrating away from the ambiguous ``app.models`` namespace. New
production code should import boundary-facing models from ``app.adapter_models``
and pure business entities from ``app.domain.models``.
"""
